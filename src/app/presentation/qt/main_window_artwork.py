from __future__ import annotations

import colorsys
import math
from pathlib import Path

import shiboken6
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest

from app.domain import Track
from app.domain.errors import DomainError
from app.domain.playback import QueueItem


class MainWindowArtworkMixin:
    def _thumb_pixmap_for_artwork_ref(
        self,
        artwork_ref: str | None,
        size: int,
    ) -> QPixmap | None:
        if not artwork_ref:
            return None
        artwork_url = self._container.services.artwork_cache.normalize_url(artwork_ref)
        if artwork_url is None:
            return None
        return self._thumb_pixmap_for_url(artwork_url, size=size)

    def _request_thumb_for_queue_row(
        self,
        artwork_ref: str | None,
        size: int,
        row: int,
    ) -> None:
        if not artwork_ref:
            return
        artwork_url = self._container.services.artwork_cache.normalize_url(artwork_ref)
        if artwork_url is None:
            return
        cache_path = self._container.services.artwork_cache.cache_path_for_url(artwork_url)
        if cache_path.exists():
            return
        self._queue_thumb_download(
            artwork_url,
            cache_path,
            on_ready=lambda: self._queue_delegate.update_row(row),
        )

    def _thumb_pixmap_for_url(self, artwork_url: str, *, size: int) -> QPixmap | None:
        cache_key = (artwork_url, size)
        cached_scaled = self._thumb_scaled_pixmap_cache.get(cache_key)
        if cached_scaled is not None:
            self._thumb_scaled_pixmap_cache.move_to_end(cache_key)
            return cached_scaled
        source_pixmap = self._thumb_source_pixmap(artwork_url)
        if source_pixmap is None:
            return None
        scaled = source_pixmap.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._thumb_scaled_pixmap_cache[cache_key] = scaled
        self._trim_thumb_scaled_cache()
        return scaled

    def _thumb_source_pixmap(self, artwork_url: str) -> QPixmap | None:
        cached_source = self._thumb_source_pixmap_cache.get(artwork_url)
        if cached_source is not None:
            self._thumb_source_pixmap_cache.move_to_end(artwork_url)
            return cached_source
        cache_path = self._container.services.artwork_cache.cache_path_for_url(artwork_url)
        if not cache_path.exists():
            return None
        pixmap = QPixmap(str(cache_path))
        if pixmap.isNull():
            return None
        pixmap = self._normalized_thumb_source_pixmap(pixmap)
        self._thumb_source_pixmap_cache[artwork_url] = pixmap
        self._trim_thumb_source_cache()
        return pixmap

    def _store_thumb_source_pixmap(self, artwork_url: str, pixmap: QPixmap) -> None:
        self._thumb_source_pixmap_cache[artwork_url] = self._normalized_thumb_source_pixmap(pixmap)
        self._trim_thumb_source_cache()
        stale_keys = [
            key for key in self._thumb_scaled_pixmap_cache
            if key[0] == artwork_url
        ]
        for key in stale_keys:
            del self._thumb_scaled_pixmap_cache[key]

    def _normalized_thumb_source_pixmap(self, pixmap: QPixmap) -> QPixmap:
        max_edge = self._THUMB_SOURCE_MAX_EDGE
        if max(pixmap.width(), pixmap.height()) <= max_edge:
            return pixmap
        return pixmap.scaled(
            max_edge,
            max_edge,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _trim_thumb_source_cache(self) -> None:
        while len(self._thumb_source_pixmap_cache) > self._THUMB_SOURCE_CACHE_LIMIT:
            self._thumb_source_pixmap_cache.popitem(last=False)

    def _trim_thumb_scaled_cache(self) -> None:
        while len(self._thumb_scaled_pixmap_cache) > self._THUMB_SCALED_CACHE_LIMIT:
            self._thumb_scaled_pixmap_cache.popitem(last=False)

    def _render_artwork(self, track: Track) -> None:
        if not track.artwork_ref:
            self._clear_artwork()
            self._set_accent_color("#DAA435")
            return

        artwork_url = self._container.services.artwork_cache.normalize_url(track.artwork_ref)
        if artwork_url is None:
            self._clear_artwork()
            self._set_accent_color("#DAA435")
            return

        cache_path = self._container.services.artwork_cache.cache_path_for_url(artwork_url)
        cached_accent = self._container.services.artwork_cache.load_accent_color(cache_path)
        if cached_accent:
            self._set_accent_color(cached_accent)
        if cache_path.exists():
            self._set_artwork_pixmap(cache_path, preferred_accent=track.accent_color)
            return

        self._pending_artwork_track_id = track.id
        request = QNetworkRequest(QUrl(artwork_url))
        request.setAttribute(QNetworkRequest.Attribute.Http2AllowedAttribute, False)
        request.setAttribute(QNetworkRequest.Attribute.HttpPipeliningAllowedAttribute, False)
        reply = self._artwork_manager.get(request)
        reply.setProperty("track_id", track.id)
        reply.setProperty("cache_path", str(cache_path))
        reply.setProperty("preferred_accent", track.accent_color)

    def _handle_artwork_downloaded(self, reply: QNetworkReply) -> None:
        thumb_artwork_url = reply.property("thumb_artwork_url")
        if isinstance(thumb_artwork_url, str) and thumb_artwork_url:
            self._handle_thumb_downloaded(reply, thumb_artwork_url)
            return

        track_id = reply.property("track_id")
        cache_path = Path(str(reply.property("cache_path")))
        preferred_accent = reply.property("preferred_accent")
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            return

        data = bytes(reply.readAll())
        reply.deleteLater()
        if not data:
            return
        try:
            self._container.services.artwork_cache.save_bytes(cache_path, data)
        except DomainError as exc:
            self._container.logger.warning("Artwork cache write failed: %s", exc)
            return
        if track_id == self._pending_artwork_track_id:
            self._set_artwork_pixmap(
                cache_path,
                preferred_accent=preferred_accent if isinstance(preferred_accent, str) else None,
            )

    def _handle_thumb_downloaded(self, reply: QNetworkReply, artwork_url: str) -> None:
        cache_path = Path(str(reply.property("cache_path")))
        labels = self._pending_thumb_labels.pop(artwork_url, [])
        callbacks = self._pending_thumb_callbacks.pop(artwork_url, [])
        self._active_thumb_downloads = max(0, self._active_thumb_downloads - 1)
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            self._start_next_thumb_downloads()
            return
        data = bytes(reply.readAll())
        reply.deleteLater()
        if not data:
            self._start_next_thumb_downloads()
            return
        try:
            self._container.services.artwork_cache.save_bytes(cache_path, data)
        except DomainError as exc:
            self._container.logger.warning("Artwork thumb cache write failed: %s", exc)
            self._start_next_thumb_downloads()
            return
        pixmap = QPixmap(str(cache_path))
        if pixmap.isNull():
            self._start_next_thumb_downloads()
            return
        self._store_thumb_source_pixmap(artwork_url, pixmap)
        for label in labels:
            if shiboken6.isValid(label):
                self._set_thumb_pixmap(label, pixmap)
        for callback in callbacks:
            callback()
        self._start_next_thumb_downloads()

    def _set_artwork_pixmap(self, path: Path, *, preferred_accent: str | None = None) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._clear_artwork()
            return
        accent = self._container.services.artwork_cache.load_accent_color(path)
        if accent is None:
            pixel_accent = self._extract_accent_color(pixmap)
            if pixel_accent and self._has_usable_accent_contrast(pixel_accent):
                accent = pixel_accent
                self._container.logger.debug(
                    "Artwork accent source=pixels image=%s color=%s preferred=%s",
                    path.name,
                    accent,
                    preferred_accent or "none",
                )
            elif preferred_accent and self._has_usable_accent_contrast(preferred_accent):
                accent = preferred_accent
                self._container.logger.debug(
                    (
                        "Artwork accent source=api-fallback image=%s color=%s "
                        "pixel_candidate=%s preferred=%s"
                    ),
                    path.name,
                    accent,
                    pixel_accent,
                    preferred_accent,
                )
            else:
                accent = "#DAA435"
                self._container.logger.debug(
                    (
                        "Artwork accent source=default-fallback image=%s color=%s "
                        "pixel_candidate=%s preferred=%s"
                    ),
                    path.name,
                    accent,
                    pixel_accent,
                    preferred_accent or "none",
                )
            try:
                self._container.services.artwork_cache.save_accent_color(path, accent)
            except DomainError as exc:
                self._container.logger.warning("Artwork accent cache write failed: %s", exc)
        self._set_accent_color(accent)
        self._artwork_label.setPixmap(
            pixmap.scaled(
                self._artwork_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _clear_artwork(self) -> None:
        self._pending_artwork_track_id = None
        self._artwork_label.clear()
        self._artwork_label.setText("No cover")

    def _extract_accent_color(self, pixmap: QPixmap) -> str | None:
        image = pixmap.toImage()
        width = image.width()
        height = image.height()
        if width <= 0 or height <= 0:
            return None
        step = self._accent_sampling_step(width, height)
        origin_x = width % step
        origin_y = height % step
        center_x = (width - 1) / 2.0
        center_y = (height - 1) / 2.0
        max_distance = math.hypot(center_x, center_y) or 1.0
        buckets: dict[tuple[int, int, int], dict[str, float]] = {}

        for y in range(origin_y, height, step):
            for x in range(origin_x, width, step):
                color = image.pixelColor(x, y)
                if color.alpha() < 40:
                    continue
                red = color.red()
                green = color.green()
                blue = color.blue()
                hue, lightness, saturation = colorsys.rgb_to_hls(
                    red / 255.0,
                    green / 255.0,
                    blue / 255.0,
                )
                if lightness < 0.08 or lightness > 0.94:
                    continue
                if saturation < 0.12:
                    continue
                key = (
                    min(35, int(hue * 36)),
                    min(7, int(lightness * 8)),
                    min(5, int(saturation * 6)),
                )
                distance = math.hypot(x - center_x, y - center_y) / max_distance
                center_weight = 1.0 - max(0.0, min(1.0, distance))
                bucket = buckets.setdefault(
                    key,
                    {
                        "count": 0.0,
                        "red": 0.0,
                        "green": 0.0,
                        "blue": 0.0,
                        "saturation": 0.0,
                        "lightness": 0.0,
                        "center": 0.0,
                    },
                )
                bucket["count"] += 1.0
                bucket["red"] += red
                bucket["green"] += green
                bucket["blue"] += blue
                bucket["saturation"] += saturation
                bucket["lightness"] += lightness
                bucket["center"] += center_weight

        if not buckets:
            return None
        total_count = sum(bucket["count"] for bucket in buckets.values()) or 1.0
        best_score = -1.0
        best_rgb = (82, 110, 232)
        for bucket in buckets.values():
            count = bucket["count"] or 1.0
            area = count / total_count
            saturation = bucket["saturation"] / count
            lightness = bucket["lightness"] / count
            center = bucket["center"] / count
            lightness_score = 1.0 - abs(lightness - 0.55) / 0.45
            lightness_score = max(0.0, min(1.0, lightness_score))
            score = (
                (area**0.55)
                * (saturation**1.45)
                * (0.25 + 0.75 * lightness_score)
                * (0.75 + 0.25 * center)
            )
            if score <= best_score:
                continue
            best_score = score
            best_rgb = (
                int(bucket["red"] / count),
                int(bucket["green"] / count),
                int(bucket["blue"] / count),
            )
        return "#{:02x}{:02x}{:02x}".format(*best_rgb)

    def _accent_sampling_step(self, width: int, height: int) -> int:
        longest_side = max(width, height)
        return max(3, min(8, longest_side // 220 or 3))

    def _has_usable_accent_contrast(self, color: str) -> bool:
        qcolor = QColor(color)
        luminance = (
            0.2126 * qcolor.redF()
            + 0.7152 * qcolor.greenF()
            + 0.0722 * qcolor.blueF()
        )
        background = 0.055
        contrast = (max(luminance, background) + 0.05) / (min(luminance, background) + 0.05)
        return contrast >= 2.2

    def _set_accent_color(self, color: str) -> None:
        if color == self._accent_color:
            return
        self._accent_color = color
        self._apply_theme()

    def _accent_text_color(self) -> str:
        accent = QColor(self._accent_color)
        luminance = (
            0.2126 * accent.redF()
            + 0.7152 * accent.greenF()
            + 0.0722 * accent.blueF()
        )
        return "#101116" if luminance > 0.58 else "#ffffff"

    def _format_year(self, year: int | None) -> str:
        return f" ({year})" if year else ""

    def _format_audio_info(self, codec: str | None, bitrate: int | None) -> str:
        if not codec or bitrate is None:
            return ""
        codec_label = self._compact_codec(codec)
        kbps = bitrate if bitrate < 1000 else round(bitrate / 1000)
        return f"{codec_label}:{max(1, kbps)}"

    def _compact_codec(self, codec: str | None) -> str:
        if not codec:
            return "?"
        normalized = codec.lower()
        for label in ("mp3", "aac", "flac", "opus", "vorbis", "alac"):
            if label in normalized:
                return label
        if "mpeg" in normalized and "layer 3" in normalized:
            return "mp3"
        return normalized.split(" ", 1)[0].split(",", 1)[0]

    def _queue_duration_ms(self, queue: tuple[QueueItem, ...]) -> int:
        return sum(item.track.duration_ms or 0 for item in queue)

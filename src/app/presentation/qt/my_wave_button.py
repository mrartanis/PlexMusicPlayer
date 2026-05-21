from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QPushButton, QWidget


class MyWaveButton(QPushButton):
    _HISTORY_WINDOW_SECONDS = 12 * 60
    _STEP_SECONDS = 2
    _MAX_PROGRESS_DELTA_MS = 5_000
    _DISPLAY_BUCKETS = 48
    _LIGHT_OUTLINE = QColor("#101116")
    _DARK_OUTLINE = QColor("#f5f7fb")

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._accent = QColor("#DAA435")
        self._accent_text = QColor("#ffffff")
        self._trailing = QColor("#efd9a8")
        self._radius = 9
        self._theme_mode = "light"
        self._history_samples: list[QColor] = []
        self._history_has_playback = False
        self._active_track_id: str | None = None
        self._last_position_ms: int | None = None
        self._pending_played_ms = 0

    def set_visuals(
        self,
        *,
        accent: str,
        accent_text: str,
        trailing: str,
        rounded: bool,
        theme_mode: str,
    ) -> None:
        self._accent = QColor(accent)
        self._accent_text = QColor(accent_text)
        self._trailing = QColor(trailing)
        self._radius = 9 if rounded else 0
        self._theme_mode = theme_mode
        if not self._history_has_playback:
            self._history_samples = []
        self.update()

    def sync_playback(
        self,
        *,
        enabled: bool,
        track_id: str | None,
        position_ms: int,
        accent: str,
    ) -> bool:
        current_color = QColor(accent)

        if not enabled or track_id is None:
            self._active_track_id = None
            self._last_position_ms = None
            self._pending_played_ms = 0
            return False

        if track_id != self._active_track_id:
            self._active_track_id = track_id
            self._last_position_ms = position_ms
            self._pending_played_ms = 0
            return False

        if self._last_position_ms is None:
            self._last_position_ms = position_ms
            return False

        delta_ms = position_ms - self._last_position_ms
        self._last_position_ms = position_ms
        if delta_ms <= 0 or delta_ms > self._MAX_PROGRESS_DELTA_MS:
            self._pending_played_ms = 0
            return False

        self._pending_played_ms += delta_ms
        step_ms = self._STEP_SECONDS * 1000
        steps = self._pending_played_ms // step_ms
        if steps <= 0:
            return False

        self._pending_played_ms %= step_ms
        for _ in range(steps):
            self._push_color_sample(current_color)
        self.update()
        return True

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect().adjusted(0, 0, -1, -1)
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        for stop, color in self._gradient_stops():
            gradient.setColorAt(stop, color)

        painter.setPen(QPen(self._accent, 1))
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, self._radius, self._radius)

        painter.setFont(self.font())
        self._draw_text_with_outline(painter, rect)

    def _gradient_stops(self) -> list[tuple[float, QColor]]:
        if not self._history_samples:
            color = self._interactive_color(QColor(self._accent))
            return [(0.0, color), (1.0, color)]

        colors = [self._interactive_color(color) for color in self._display_history()]
        count = len(colors)
        cell = 1.0 / max(1, count)
        blend_half = cell * 0.9
        stops: list[tuple[float, QColor]] = [(0.0, colors[0])]
        for index in range(count - 1):
            boundary = (index + 1) * cell
            stops.append((max(0.0, boundary - blend_half), colors[index]))
            stops.append((min(1.0, boundary + blend_half), colors[index + 1]))
        stops.append((1.0, colors[-1]))
        return stops

    def _interactive_color(self, color: QColor) -> QColor:
        adjusted = QColor(color)
        if self.isDown():
            adjusted = self._mix_colors(adjusted, QColor("#000000"), 0.12)
        elif self.underMouse():
            adjusted = self._mix_colors(adjusted, QColor("#ffffff"), 0.08)
        return adjusted

    def _display_history(self) -> list[QColor]:
        bucketed = self._bucketed_history()
        if len(bucketed) < 2:
            return bucketed

        weights = (1, 2, 3, 4, 3, 2, 1)
        radius = len(weights) // 2
        smoothed: list[QColor] = []
        for index in range(len(bucketed)):
            red = green = blue = total = 0
            for offset, weight in enumerate(weights, start=-radius):
                sample_index = min(max(index + offset, 0), len(bucketed) - 1)
                color = bucketed[sample_index]
                red += color.red() * weight
                green += color.green() * weight
                blue += color.blue() * weight
                total += weight
            smoothed.append(
                QColor(
                    round(red / total),
                    round(green / total),
                    round(blue / total),
                )
            )
        return smoothed

    def _bucketed_history(self) -> list[QColor]:
        if len(self._history_samples) < 2:
            return list(self._history_samples)

        bucket_size = max(1, len(self._history_samples) // self._DISPLAY_BUCKETS)
        bucketed: list[QColor] = []
        for start in range(0, len(self._history_samples), bucket_size):
            chunk = self._history_samples[start : start + bucket_size]
            red = sum(color.red() for color in chunk)
            green = sum(color.green() for color in chunk)
            blue = sum(color.blue() for color in chunk)
            count = len(chunk)
            bucketed.append(
                QColor(
                    round(red / count),
                    round(green / count),
                    round(blue / count),
                )
            )
        return bucketed

    def _seed_history(self) -> None:
        self._history_has_playback = False
        self._history_samples = []

    def _push_color_sample(self, color: QColor) -> None:
        if not self._history_samples:
            self._history_samples = [QColor(color) for _ in range(self._sample_count())]
        self._history_has_playback = True
        self._history_samples.insert(0, QColor(color))
        max_samples = self._sample_count()
        if len(self._history_samples) > max_samples:
            del self._history_samples[max_samples:]

    def _sample_count(self) -> int:
        return self._HISTORY_WINDOW_SECONDS // self._STEP_SECONDS

    def export_history(self) -> list[str]:
        if not self._history_has_playback:
            return []
        return [color.name().lower() for color in self._history_samples]

    def restore_history(self, samples: list[str]) -> None:
        restored: list[QColor] = []
        for sample in samples[: self._sample_count()]:
            color = QColor(sample)
            if not color.isValid():
                continue
            restored.append(color)
        self._history_samples = restored
        self._history_has_playback = bool(restored)
        self._active_track_id = None
        self._last_position_ms = None
        self._pending_played_ms = 0
        self.update()

    def _draw_text_with_outline(self, painter: QPainter, rect) -> None:
        if self._theme_mode == "dark":
            text_color = QColor("#000000")
            outline_color = QColor(self._DARK_OUTLINE)
        else:
            text_color = QColor("#ffffff")
            outline_color = QColor(self._LIGHT_OUTLINE)

        outline_color.setAlpha(112)
        for dx, dy in ((0, 1), (1, 0)):
            painter.setPen(outline_color)
            painter.drawText(rect.translated(dx, dy), Qt.AlignmentFlag.AlignCenter, self.text())
        painter.setPen(text_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())

    def _mix_colors(self, first: QColor, second: QColor, ratio: float) -> QColor:
        ratio = max(0.0, min(1.0, ratio))
        inverse = 1.0 - ratio
        return QColor(
            round(first.red() * inverse + second.red() * ratio),
            round(first.green() * inverse + second.green() * ratio),
            round(first.blue() * inverse + second.blue() * ratio),
        )

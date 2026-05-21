from __future__ import annotations

import http.server
import os
import ssl
import threading
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass, field
from socketserver import ThreadingMixIn
from uuid import uuid4

import certifi
import miniaudio

from app.domain import LibraryCacheRepo, Logger, Track, WaveformState

_WAVEFORM_BIN_COUNT = 100
_ANALYSIS_MIN_DELTA_BYTES = 512 * 1024
_PROXY_CHUNK_SIZE = 64 * 1024


@dataclass(slots=True)
class _ByteRange:
    start: int
    end: int


@dataclass(slots=True)
class _ProxySession:
    session_id: str
    track: Track
    track_id: str
    track_duration_ms: int | None
    upstream_url: str
    lock: threading.Lock = field(default_factory=threading.Lock)
    byte_ranges: list[_ByteRange] = field(default_factory=list)
    contiguous_data: bytearray = field(default_factory=bytearray)
    pending_chunks: dict[int, bytes] = field(default_factory=dict)
    total_size_bytes: int | None = None
    content_type: str | None = None
    contiguous_bytes: int = 0
    waveform_bins: tuple[float, ...] = ()
    waveform_known_position_ms: int = 0
    waveform_mode: str = "plain"
    analysis_in_flight: bool = False
    last_analysis_size_bytes: int = 0
    closed: bool = False

    def local_url(self, *, port: int) -> str:
        return f"http://127.0.0.1:{port}/stream/{self.session_id}"


class _ThreadingHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class StreamProxyService:
    def __init__(
        self,
        *,
        logger: Logger,
        library_cache_repo: LibraryCacheRepo | None = None,
    ) -> None:
        self._logger = logger
        self._library_cache_repo = library_cache_repo
        self._sessions_by_id: dict[str, _ProxySession] = {}
        self._sessions_by_track_id: dict[str, _ProxySession] = {}
        self._lock = threading.Lock()
        self._server: _ThreadingHTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self._ssl_context = self._build_ssl_context()

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("stream proxy server is not running")
        return int(self._server.server_port)

    def create_session(self, *, track: Track, stream_ref: str) -> str:
        if not self._ensure_server_started():
            return stream_ref
        self.close_track_session(track.id)
        session = _ProxySession(
            session_id=str(uuid4()),
            track=track,
            track_id=track.id,
            track_duration_ms=track.duration_ms,
            upstream_url=stream_ref,
        )
        if track.waveform_bins and track.duration_ms:
            session.waveform_bins = track.waveform_bins
            session.waveform_known_position_ms = track.duration_ms
            session.waveform_mode = "cached"
        with self._lock:
            self._sessions_by_id[session.session_id] = session
            self._sessions_by_track_id[track.id] = session
        return session.local_url(port=self.port)

    def close_track_session(self, track_id: str) -> None:
        with self._lock:
            session = self._sessions_by_track_id.pop(track_id, None)
            if session is None:
                return
            self._sessions_by_id.pop(session.session_id, None)
        self._close_session(session)

    def get_waveform_state(self, track_id: str | None) -> WaveformState:
        if track_id is None:
            return WaveformState()
        with self._lock:
            session = self._sessions_by_track_id.get(track_id)
        if session is None:
            return WaveformState()
        with session.lock:
            buffered_position_ms = self._scaled_position_ms(
                contiguous_bytes=session.contiguous_bytes,
                total_size_bytes=session.total_size_bytes,
                duration_ms=session.track_duration_ms,
            )
            return WaveformState(
                buffered_position_ms=buffered_position_ms,
                waveform_bins=session.waveform_bins,
                waveform_known_position_ms=session.waveform_known_position_ms,
                waveform_mode=session.waveform_mode,
            )

    def shutdown(self) -> None:
        with self._lock:
            sessions = list(self._sessions_by_id.values())
            self._sessions_by_id.clear()
            self._sessions_by_track_id.clear()
        for session in sessions:
            self._close_session(session)
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    def _ensure_server_started(self) -> bool:
        if self._server is not None:
            return True
        try:
            self._server = _ThreadingHTTPServer(("127.0.0.1", 0), self._build_handler())
        except OSError as exc:
            self._logger.warning("Failed to start local stream proxy: %s", exc)
            self._server = None
            return False
        self._server_thread = threading.Thread(
            target=self._server.serve_forever,
            name="yaymp-stream-proxy",
            daemon=True,
        )
        self._server_thread.start()
        return True

    def _build_ssl_context(self) -> ssl.SSLContext:
        if os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR"):
            return ssl.create_default_context()
        return ssl.create_default_context(cafile=certifi.where())

    def _build_handler(self):
        service = self

        class ProxyHandler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_HEAD(self) -> None:  # noqa: N802
                service._handle_proxy_request(self, send_body=False)

            def do_GET(self) -> None:  # noqa: N802
                service._handle_proxy_request(self, send_body=True)

            def log_message(self, format: str, *args) -> None:  # noqa: A003
                del format, args

        return ProxyHandler

    def _handle_proxy_request(
        self,
        handler: http.server.BaseHTTPRequestHandler,
        *,
        send_body: bool,
    ) -> None:
        session = self._session_for_path(handler.path)
        if session is None:
            handler.send_error(404)
            return

        request = urllib.request.Request(session.upstream_url, method=handler.command)
        range_header = handler.headers.get("Range")
        if range_header:
            request.add_header("Range", range_header)

        try:
            with urllib.request.urlopen(
                request,
                timeout=20,
                context=self._ssl_context,
            ) as response:
                self._forward_headers(handler, response)
                if not send_body:
                    return
                start_offset = _range_start(range_header)
                bytes_written = 0
                while True:
                    chunk = response.read(_PROXY_CHUNK_SIZE)
                    if not chunk:
                        break
                    handler.wfile.write(chunk)
                    self._record_download(
                        session,
                        start_offset=start_offset + bytes_written,
                        chunk=chunk,
                        content_type=response.headers.get("Content-Type"),
                        total_size_bytes=_response_total_size(response.headers, start_offset),
                    )
                    bytes_written += len(chunk)
        except urllib.error.HTTPError as exc:
            body = exc.read()
            handler.send_response(exc.code)
            for header_name, header_value in exc.headers.items():
                if header_name.lower() == "transfer-encoding":
                    continue
                handler.send_header(header_name, header_value)
            handler.end_headers()
            if send_body and body:
                handler.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            self._logger.debug("Stream proxy client disconnected for %s", session.track_id)
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Stream proxy failed for %s: %s", session.track_id, exc)
            if not handler.wfile.closed:
                handler.send_error(502)

    def _session_for_path(self, path: str) -> _ProxySession | None:
        _, _, suffix = path.partition("/stream/")
        if not suffix:
            return None
        session_id = suffix.split("?", 1)[0]
        with self._lock:
            return self._sessions_by_id.get(session_id)

    def _forward_headers(
        self,
        handler: http.server.BaseHTTPRequestHandler,
        response,
    ) -> None:
        handler.send_response(getattr(response, "status", 200))
        for header_name, header_value in response.headers.items():
            if header_name.lower() in {"connection", "transfer-encoding"}:
                continue
            handler.send_header(header_name, header_value)
        handler.end_headers()

    def _record_download(
        self,
        session: _ProxySession,
        *,
        start_offset: int,
        chunk: bytes,
        content_type: str | None,
        total_size_bytes: int | None,
    ) -> None:
        with session.lock:
            if session.closed:
                return
            if total_size_bytes is not None and total_size_bytes > 0:
                session.total_size_bytes = total_size_bytes
            if content_type:
                session.content_type = content_type
            session.byte_ranges = _merge_ranges(
                session.byte_ranges,
                _ByteRange(start=start_offset, end=start_offset + len(chunk)),
            )
            _append_contiguous_data(session, start_offset, chunk)
            session.contiguous_bytes = _contiguous_prefix_length(session.byte_ranges)
            if session.waveform_mode == "plain" and _looks_like_decodable_audio(session):
                session.waveform_mode = "mp3_partial"
            self._maybe_schedule_analysis(session)

    def _maybe_schedule_analysis(self, session: _ProxySession) -> None:
        if session.waveform_mode != "mp3_partial":
            return
        if session.track_duration_ms is None or session.track_duration_ms <= 0:
            return
        if session.analysis_in_flight:
            return
        contiguous_size = len(session.contiguous_data)
        if contiguous_size <= session.last_analysis_size_bytes:
            return
        if (
            contiguous_size - session.last_analysis_size_bytes < _ANALYSIS_MIN_DELTA_BYTES
            and session.total_size_bytes != contiguous_size
        ):
            return

        session.analysis_in_flight = True
        data_snapshot = bytes(session.contiguous_data)
        is_complete = (
            session.total_size_bytes is not None
            and contiguous_size >= session.total_size_bytes
        )
        self._logger.debug(
            (
                "Waveform analysis scheduled track=%s contiguous=%s total=%s "
                "duration_ms=%s complete=%s last_analysis=%s"
            ),
            session.track_id,
            contiguous_size,
            session.total_size_bytes,
            session.track_duration_ms,
            is_complete,
            session.last_analysis_size_bytes,
        )
        thread = threading.Thread(
            target=self._analyze_waveform,
            args=(session.session_id, contiguous_size, data_snapshot, is_complete),
            daemon=True,
            name=f"yaymp-waveform-{session.track_id}",
        )
        thread.start()

    def _analyze_waveform(
        self,
        session_id: str,
        contiguous_size: int,
        data_snapshot: bytes,
        is_complete: bool,
    ) -> None:
        with self._lock:
            session = self._sessions_by_id.get(session_id)
        if session is None:
            return
        try:
            with session.lock:
                if session.closed:
                    return
                duration_ms = session.track_duration_ms or 0
            bins, known_position_ms = _decode_audio_bins(
                data_snapshot,
                duration_ms=duration_ms,
                bin_count=_WAVEFORM_BIN_COUNT,
                is_complete=is_complete,
            )
            with session.lock:
                if not session.closed:
                    session.waveform_bins = bins
                    session.waveform_known_position_ms = known_position_ms
                    session.last_analysis_size_bytes = max(
                        session.last_analysis_size_bytes,
                        contiguous_size,
                    )
                    if is_complete and self._library_cache_repo is not None:
                        self._library_cache_repo.save_track_metadata(
                            Track(
                                id=session.track.id,
                                title=session.track.title,
                                artists=session.track.artists,
                                version=session.track.version,
                                artist_ids=session.track.artist_ids,
                                album_id=session.track.album_id,
                                album_title=session.track.album_title,
                                album_year=session.track.album_year,
                                duration_ms=session.track.duration_ms,
                                stream_ref=session.track.stream_ref,
                                stream_ref_cached_at=session.track.stream_ref_cached_at,
                                artwork_ref=session.track.artwork_ref,
                                accent_color=session.track.accent_color,
                                waveform_bins=tuple(bins),
                                available=session.track.available,
                                is_liked=session.track.is_liked,
                            )
                        )
                    self._logger.debug(
                        (
                            "Waveform analysis complete track=%s contiguous=%s total=%s "
                            "known_ms=%s duration_ms=%s bins=%s complete=%s"
                        ),
                        session.track_id,
                        contiguous_size,
                        session.total_size_bytes,
                        known_position_ms,
                        duration_ms,
                        len(bins),
                        is_complete,
                    )
        except Exception as exc:  # noqa: BLE001
            with session.lock:
                session.last_analysis_size_bytes = max(
                    session.last_analysis_size_bytes,
                    contiguous_size,
                )
                if is_complete:
                    session.waveform_mode = "decode_failed"
            self._logger.debug(
                (
                    "Waveform analysis deferred track=%s contiguous=%s total=%s "
                    "duration_ms=%s complete=%s error=%s"
                ),
                session.track_id,
                contiguous_size,
                session.total_size_bytes if session is not None else None,
                duration_ms if "duration_ms" in locals() else None,
                is_complete,
                exc,
            )
        finally:
            with session.lock:
                session.analysis_in_flight = False
                should_catch_up = (
                    not session.closed
                    and session.waveform_mode == "mp3_partial"
                    and len(session.contiguous_data) > session.last_analysis_size_bytes
                )
                if should_catch_up:
                    self._logger.debug(
                        (
                            "Waveform analysis catch-up track=%s contiguous=%s "
                            "last_analysis=%s total=%s"
                        ),
                        session.track_id,
                        len(session.contiguous_data),
                        session.last_analysis_size_bytes,
                        session.total_size_bytes,
                    )
                    self._maybe_schedule_analysis(session)

    def _close_session(self, session: _ProxySession) -> None:
        with session.lock:
            session.closed = True
            session.pending_chunks.clear()
            session.contiguous_data.clear()

    def _scaled_position_ms(
        self,
        *,
        contiguous_bytes: int,
        total_size_bytes: int | None,
        duration_ms: int | None,
    ) -> int | None:
        if total_size_bytes is None or total_size_bytes <= 0 or duration_ms is None:
            return None
        ratio = max(0.0, min(1.0, contiguous_bytes / total_size_bytes))
        return int(duration_ms * ratio)


def _merge_ranges(ranges: Sequence[_ByteRange], new_range: _ByteRange) -> list[_ByteRange]:
    merged = sorted((*ranges, new_range), key=lambda item: item.start)
    result: list[_ByteRange] = []
    for item in merged:
        if not result or item.start > result[-1].end:
            result.append(_ByteRange(start=item.start, end=item.end))
            continue
        result[-1].end = max(result[-1].end, item.end)
    return result


def _contiguous_prefix_length(ranges: Sequence[_ByteRange]) -> int:
    if not ranges or ranges[0].start > 0:
        return 0
    end = ranges[0].end
    for item in ranges[1:]:
        if item.start > end:
            break
        end = max(end, item.end)
    return end


def _range_start(range_header: str | None) -> int:
    if not range_header or "=" not in range_header:
        return 0
    _, _, value = range_header.partition("=")
    start_text, _, _ = value.partition("-")
    try:
        return max(0, int(start_text))
    except ValueError:
        return 0


def _response_total_size(headers, start_offset: int) -> int | None:
    content_range = headers.get("Content-Range")
    if content_range and "/" in content_range:
        _, _, total_text = content_range.partition("/")
        if total_text.isdigit():
            return int(total_text)
    content_length = headers.get("Content-Length")
    if content_length and content_length.isdigit():
        return start_offset + int(content_length)
    return None


def _looks_like_decodable_audio(session: _ProxySession) -> bool:
    content_type = (session.content_type or "").lower()
    if any(
        marker in content_type
        for marker in (
            "audio/mpeg",
            "audio/mp3",
            "audio/aac",
            "audio/x-aac",
            "audio/aacp",
            "audio/flac",
            "audio/x-flac",
            "audio/ogg",
            "audio/opus",
            "audio/vorbis",
            "audio/wav",
            "audio/wave",
            "audio/x-wav",
            "audio/mp4",
            "audio/x-m4a",
            "audio/alac",
        )
    ):
        return True

    header = bytes(session.contiguous_data[:64])
    if header.startswith(b"ID3"):
        return True
    if header.startswith(b"fLaC"):
        return True
    if header.startswith(b"OggS"):
        return True
    if header.startswith(b"RIFF") and b"WAVE" in header[:16]:
        return True
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return True

    frame = header[:2]
    if len(frame) < 2:
        return False
    return frame[0] == 0xFF and (frame[1] & 0xE0) == 0xE0


def _append_contiguous_data(session: _ProxySession, start_offset: int, chunk: bytes) -> None:
    contiguous_end = len(session.contiguous_data)
    if start_offset <= contiguous_end:
        overlap = contiguous_end - start_offset
        if overlap < len(chunk):
            session.contiguous_data.extend(chunk[overlap:])
        _drain_pending_chunks(session)
        return
    existing = session.pending_chunks.get(start_offset)
    if existing is None or len(chunk) > len(existing):
        session.pending_chunks[start_offset] = chunk
    _drain_pending_chunks(session)


def _drain_pending_chunks(session: _ProxySession) -> None:
    while True:
        contiguous_end = len(session.contiguous_data)
        direct = session.pending_chunks.pop(contiguous_end, None)
        if direct is not None:
            session.contiguous_data.extend(direct)
            continue

        appended = False
        for start in sorted(session.pending_chunks):
            if start > contiguous_end:
                break
            chunk = session.pending_chunks.pop(start)
            overlap = contiguous_end - start
            if overlap < len(chunk):
                session.contiguous_data.extend(chunk[overlap:])
                appended = True
                break
        if not appended:
            break


def _decode_audio_bins(
    data: bytes,
    *,
    duration_ms: int,
    bin_count: int,
    is_complete: bool,
) -> tuple[tuple[float, ...], int]:
    decoded = miniaudio.decode(
        data,
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=2,
        sample_rate=44_100,
    )
    samples = decoded.samples
    channels = max(1, decoded.nchannels)
    frames = len(samples) // channels
    if frames <= 0:
        raise ValueError("decoded audio has no frames")

    decoded_duration_ms = int(frames * 1000 / decoded.sample_rate)
    known_position_ms = duration_ms if is_complete else min(duration_ms, decoded_duration_ms)
    if known_position_ms <= 0:
        raise ValueError("decoded audio has no known duration")

    if is_complete:
        known_bin_count = bin_count
    else:
        known_bin_count = max(
            1,
            min(bin_count, round(bin_count * known_position_ms / duration_ms)),
        )
    frames_per_bin = max(1, frames // known_bin_count)
    bins = [0.0] * bin_count
    max_possible = float(32767)

    for bin_index in range(known_bin_count):
        frame_start = bin_index * frames_per_bin
        frame_end = (
            frames
            if bin_index == known_bin_count - 1
            else min(frames, frame_start + frames_per_bin)
        )
        if frame_start >= frame_end:
            continue
        amplitude_sum = 0.0
        sample_count = 0
        for frame in range(frame_start, frame_end):
            base_index = frame * channels
            for channel in range(channels):
                amplitude_sum += abs(samples[base_index + channel]) / max_possible
                sample_count += 1
        bins[bin_index] = amplitude_sum / sample_count if sample_count else 0.0

    peak = max(bins[:known_bin_count]) if known_bin_count else 0.0
    if peak > 0:
        bins = [min(1.0, value / peak) for value in bins]
    return tuple(bins), known_position_ms

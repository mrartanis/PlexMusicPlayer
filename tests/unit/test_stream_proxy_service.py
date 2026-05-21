from __future__ import annotations

from app.domain import Track
from app.infrastructure.playback.stream_proxy_service import (
    _looks_like_decodable_audio,
    _ProxySession,
)


def _session(*, content_type: str | None = None, data: bytes = b"") -> _ProxySession:
    session = _ProxySession(
        session_id="session",
        track=Track(id="track", title="Track", artists=("Artist",)),
        track_id="track",
        track_duration_ms=180_000,
        upstream_url="https://example.test/audio",
    )
    session.content_type = content_type
    session.contiguous_data.extend(data)
    return session


def test_decodable_audio_sniffer_accepts_common_audio_content_types() -> None:
    assert _looks_like_decodable_audio(_session(content_type="audio/flac"))
    assert _looks_like_decodable_audio(_session(content_type="audio/ogg"))
    assert _looks_like_decodable_audio(_session(content_type="audio/mp4"))


def test_decodable_audio_sniffer_accepts_common_container_headers() -> None:
    assert _looks_like_decodable_audio(_session(data=b"fLaC" + b"\x00" * 32))
    assert _looks_like_decodable_audio(_session(data=b"OggS" + b"\x00" * 32))
    assert _looks_like_decodable_audio(_session(data=b"RIFF\x00\x00\x00\x00WAVEfmt "))
    assert _looks_like_decodable_audio(_session(data=b"\x00\x00\x00\x18ftypM4A "))


def test_decodable_audio_sniffer_rejects_unknown_payload() -> None:
    assert not _looks_like_decodable_audio(_session(data=b"not-audio-data"))

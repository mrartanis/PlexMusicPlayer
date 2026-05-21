from __future__ import annotations

from app.infrastructure.persistence.file_artwork_cache import FileArtworkCache


def test_file_artwork_cache_normalizes_yandex_cover_refs(tmp_path) -> None:
    cache = FileArtworkCache(cache_dir=tmp_path)

    assert cache.normalize_url("avatars.yandex.net/get-music-content/%%") == (
        "https://avatars.yandex.net/get-music-content/600x600"
    )
    assert cache.normalize_url("//avatars.yandex.net/get-music-content/%%") == (
        "https://avatars.yandex.net/get-music-content/600x600"
    )
    assert cache.normalize_url("https://example.test/%%") == "https://example.test/600x600"
    assert cache.normalize_url(" ") is None


def test_file_artwork_cache_saves_bytes_to_stable_url_path(tmp_path) -> None:
    cache = FileArtworkCache(cache_dir=tmp_path)
    path = cache.cache_path_for_url("https://example.test/cover.jpg")

    cache.save_bytes(path, b"image")

    assert path.parent == tmp_path
    assert path.read_bytes() == b"image"


def test_file_artwork_cache_round_trips_accent_color_next_to_artwork(tmp_path) -> None:
    cache = FileArtworkCache(cache_dir=tmp_path)
    path = cache.cache_path_for_url("https://example.test/cover.jpg")

    cache.save_accent_color(path, "#526ee8")

    assert cache.accent_path_for_artwork_path(path).name.endswith(".img.accent")
    assert cache.load_accent_color(path) == "#526ee8"

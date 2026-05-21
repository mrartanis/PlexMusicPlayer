from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from app.domain.errors import StorageError

_ARTWORK_SIZE = "600x600"


class FileArtworkCache:
    def __init__(self, *, cache_dir: Path) -> None:
        self._cache_dir = cache_dir

    def normalize_url(self, artwork_ref: str) -> str | None:
        value = artwork_ref.strip()
        if not value:
            return None
        if value.startswith("http://") or value.startswith("https://"):
            return value.replace("%%", _ARTWORK_SIZE)
        if value.startswith("//"):
            return f"https:{value}".replace("%%", _ARTWORK_SIZE)
        if "/" in value:
            return value.replace("%%", _ARTWORK_SIZE)
        return f"https://{value}".replace("%%", _ARTWORK_SIZE)

    def cache_path_for_url(self, artwork_url: str) -> Path:
        digest = sha256(artwork_url.encode("utf-8")).hexdigest()
        return self._cache_dir / f"{digest}.img"

    def accent_path_for_artwork_path(self, artwork_path: Path) -> Path:
        return artwork_path.with_suffix(f"{artwork_path.suffix}.accent")

    def load_accent_color(self, artwork_path: Path) -> str | None:
        path = self.accent_path_for_artwork_path(artwork_path)
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if len(value) == 7 and value.startswith("#"):
            return value
        return None

    def save_accent_color(self, artwork_path: Path, color: str) -> None:
        path = self.accent_path_for_artwork_path(artwork_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(color, encoding="utf-8")
        except OSError as exc:
            raise StorageError("Failed to save artwork accent cache file") from exc

    def save_bytes(self, path: Path, data: bytes) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as exc:
            raise StorageError("Failed to save artwork cache file") from exc

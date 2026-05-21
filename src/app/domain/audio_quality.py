from __future__ import annotations

from enum import Enum


class AudioQuality(str, Enum):
    HQ = "hq"
    SD = "sd"
    LQ = "lq"


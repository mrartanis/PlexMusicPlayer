#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"

pause_if_interactive() {
    if [[ -t 0 && -t 1 ]]; then
        read -r -p "$1"
    fi
}

cd "${PROJECT_ROOT}"

if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "Missing virtualenv interpreter: ${VENV_PYTHON}"
    echo "Create it first:"
    echo "  python3 -m venv .venv"
    echo "  .venv/bin/python -m pip install -e '.[dev]'"
    pause_if_interactive "Press Enter to close..."
    exit 1
fi

export PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
export PLEX_MUSIC_PLAYER_PLAYBACK_BACKEND="${PLEX_MUSIC_PLAYER_PLAYBACK_BACKEND:-mpv}"
export PLEX_MUSIC_PLAYER_LOG_LEVEL="${PLEX_MUSIC_PLAYER_LOG_LEVEL:-DEBUG}"

"${VENV_PYTHON}" -m app

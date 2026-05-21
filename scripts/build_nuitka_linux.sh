#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
OUTPUT_DIR="${PROJECT_ROOT}/build/nuitka"
APP_NAME="PlexMusicPlayer"
DISPLAY_NAME="Plex Music Player"
ICON_NAME="plex-music-player"
APPDIR="${OUTPUT_DIR}/${APP_NAME}.AppDir"
APP_LIB_DIR="${APPDIR}/usr/lib"
NUITKA_STEM="nuitka_entry"
BUILT_DIST_DIR="${OUTPUT_DIR}/${NUITKA_STEM}.dist"
DIST_DIR="${OUTPUT_DIR}/${APP_NAME}.dist"
MPV_LIBRARY="${PLEX_MUSIC_PLAYER_MPV_LIBRARY:-}"
MPV_LIBRARY_NAME=""
APP_ICON="${PROJECT_ROOT}/assets/plex_music_player_256.png"

cd "${PROJECT_ROOT}"

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "This script builds the Linux Nuitka standalone/AppDir only."
    exit 1
fi

if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "Missing virtualenv interpreter: ${VENV_PYTHON}"
    echo "Create it first:"
    echo "  python3 -m venv .venv"
    echo "  .venv/bin/python -m pip install -e '.[dev,packaging]'"
    exit 1
fi

if [[ -z "${MPV_LIBRARY}" ]]; then
    MPV_LIBRARY="$(ldconfig -p | awk '/libmpv\.so\.(2|1) / { print $NF; exit }')"
fi

if [[ -z "${MPV_LIBRARY}" || ! -f "${MPV_LIBRARY}" ]]; then
    echo "Missing libmpv shared library. Install libmpv1/libmpv2 or set PLEX_MUSIC_PLAYER_MPV_LIBRARY."
    exit 1
fi

if [[ ! -f "${APP_ICON}" ]]; then
    echo "Missing app icon: ${APP_ICON}"
    exit 1
fi

MPV_LIBRARY_NAME="$(basename "${MPV_LIBRARY}")"

mkdir -p "${OUTPUT_DIR}"
rm -rf \
    "${OUTPUT_DIR}/${NUITKA_STEM}.build" \
    "${BUILT_DIST_DIR}" \
    "${DIST_DIR}" \
    "${OUTPUT_DIR}/${NUITKA_STEM}.onefile-build" \
    "${APPDIR}"

"${VENV_PYTHON}" -m nuitka \
    --standalone \
    --plugin-enable=pyside6 \
    --include-module=_cffi_backend \
    --include-package=certifi \
    --include-package-data=certifi \
    --include-package=cffi \
    --include-package=miniaudio \
    --include-package=app \
    --include-package-data=app.presentation.qt \
    --include-data-files="${MPV_LIBRARY}=lib/${MPV_LIBRARY_NAME}" \
    --output-dir="${OUTPUT_DIR}" \
    --output-filename="${APP_NAME}" \
    tools/nuitka_entry.py

mv "${BUILT_DIST_DIR}" "${DIST_DIR}"

mkdir -p \
    "${APPDIR}/usr/bin" \
    "${APPDIR}/usr/lib" \
    "${APPDIR}/usr/share/applications" \
    "${APPDIR}/usr/share/icons/hicolor/256x256/apps"
cp -a "${DIST_DIR}/." "${APPDIR}/usr/bin/"
cp -f "${MPV_LIBRARY}" "${APP_LIB_DIR}/${MPV_LIBRARY_NAME}"
chmod u+rw "${APP_LIB_DIR}/${MPV_LIBRARY_NAME}"
"${VENV_PYTHON}" tools/bundle_linux_libs.py \
    --root-library "${APP_LIB_DIR}/${MPV_LIBRARY_NAME}" \
    --target-dir "${APP_LIB_DIR}"

cat >"${APPDIR}/AppRun" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
APPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export LD_LIBRARY_PATH="${APPDIR}/usr/lib:${APPDIR}/usr/bin/lib:${LD_LIBRARY_PATH:-}"
exec "${APPDIR}/usr/bin/${APP_NAME}" "$@"
EOF
chmod +x "${APPDIR}/AppRun"

cat >"${APPDIR}/${ICON_NAME}.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=${DISPLAY_NAME}
Exec=${APP_NAME}
Icon=${ICON_NAME}
Categories=AudioVideo;Audio;Player;
Terminal=false
EOF
cp "${APPDIR}/${ICON_NAME}.desktop" "${APPDIR}/usr/share/applications/${ICON_NAME}.desktop"
cp "${APP_ICON}" "${APPDIR}/${ICON_NAME}.png"
cp "${APP_ICON}" "${APPDIR}/usr/share/icons/hicolor/256x256/apps/${ICON_NAME}.png"

echo "Built: ${DIST_DIR}"
echo "Built AppDir: ${APPDIR}"

# syntax=docker/dockerfile:1.4

FROM ubuntu:noble as base

ARG TARGETARCH
ENV DEBIAN_FRONTEND=noninteractive

# Configure dpkg to use unsafe io for speed
RUN echo "force-unsafe-io" > /etc/dpkg/dpkg.cfg.d/force-unsafe-io

# Add labels for better cache control
LABEL org.opencontainers.image.source="https://github.com/yourusername/PlexMusicPlayer"
LABEL org.opencontainers.image.description="Plex Music Player for ${TARGETARCH}"

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-venv \
    python3-pyqt6 \
    python3-pyqt6.qtmultimedia \
    build-essential \
    python3-dev

# Stage 2: Python dependencies
FROM base AS dependencies
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/usr/lib/python3/dist-packages:${PYTHONPATH}"

WORKDIR /app

SHELL ["/bin/bash", "-c"]
RUN pip install plexapi pyinstaller

# Verify PyQt6 is available
RUN python3 -c "import PyQt6"

# Stage 3: Build application
FROM dependencies AS builder
COPY . /app
RUN --mount=type=cache,target=/root/.cache/pip \
    source /opt/venv/bin/activate && \
    pyinstaller -F --add-data "MusicApp.iconset/icon_256x256.png:icon" plex_music_player/__main__.py && \
    mv dist/__main__ PlexMusicPlayer_linux_${TARGETARCH}

FROM scratch
COPY --from=builder /app/PlexMusicPlayer_linux* /


FROM ubuntu:22.04

ARG TARGETARCH
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg curl \
 && add-apt-repository -y ppa:deadsnakes/ppa \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
    python3.12 python3.12-dev clang libpipewire-0.3-0 pipewire libxcb-cursor0 patchelf zlib1g-dev zlib1g libz-dev

RUN if [ "$TARGETARCH" = "arm64" ]; then \
 add-apt-repository universe && apt-get update && apt-get install -y qt6-base-dev qmake6 qmake6-bin; \
fi

RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12 
COPY . /app
WORKDIR /app

RUN python3.12 -m pip install --upgrade pip && python3.12 -m pip install -r requirements.txt
RUN CC=clang CXX=clang++ nuitka --onefile --plugin-enable=pyqt6 plex_music_player/__main__.py
RUN chmod +x __main__.bin && \
    if [ "$TARGETARCH" = "arm64" ]; then \
        ls -lah; \
        mv __main__.bin PlexMusicPlayer_linux_arm64; \
    elif [ "$TARGETARCH" = "amd64" ]; then \
        ls -lah; \ 
        mv __main__.bin PlexMusicPlayer_linux_x86_64; \
    else \
        mv __main__.bin PlexMusicPlayer_linux_${TARGETARCH}; \
        ls -lah; \
    fi

CMD ["sleep", "infinity"]

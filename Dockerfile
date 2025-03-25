FROM ubuntu:22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg \
 && add-apt-repository -y ppa:deadsnakes/ppa \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
    python3.12 python-pip \
    clang libpipewire-0.3-0 pipewire libxcb-cursor0 patchelf
COPY . /app
WORKDIR /app

RUN python3 -m pip install --upgrade pip && python3 -m pip install -r requirements.txt
RUN CC=clang CXX=clang++ nuitka --onefile --plugin-enable=pyqt6 plex_music_player/__main__.py \
    && chmod +x __main__.bin && mv __main__.bin PlexMusicPlayer_linux_${TARGETARCH}

CMD ["sleep", "infinity"]

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg curl \
 && add-apt-repository -y ppa:deadsnakes/ppa \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
    python3.12 python3.12-dev clang libpipewire-0.3-0 pipewire libxcb-cursor0 patchelf zlib1g-dev zlib1g

RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12 
COPY . /app
WORKDIR /app

RUN python3.12 -m pip install --upgrade pip && python3.12 -m pip install -r requirements.txt
RUN CC=clang CXX=clang++ nuitka --onefile --plugin-enable=pyqt6 plex_music_player/__main__.py \
    && chmod +x __main__.bin && mv __main__.bin PlexMusicPlayer_linux_${TARGETARCH}

CMD ["sleep", "infinity"]

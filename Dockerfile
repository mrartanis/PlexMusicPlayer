FROM ubuntu:22.04

RUN apt update && apt install -y software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt update \
    && apt install -y python3.12 python3.12-distutils python3.12-venv python3-pip clang libpipewire-0.3-0 pipewire libxcb-cursor0 patchelf \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3

COPY . /app
WORKDIR /app

RUN python3 -m pip install --upgrade pip && python3 -m pip install -r requirements.txt
RUN CC=clang CXX=clang++ python3 -m pip install nuitka \
    && nuitka --onefile --plugin-enable=pyqt6 plex_music_player/__main__.py \
    && chmod +x __main__.bin && mv __main__.bin PlexMusicPlayer_linux_${TARGETARCH}

CMD ["sleep", "infinity"]

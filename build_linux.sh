# Hey!
# To build it you can use clang18, but you can use any compiler.
# Also, packages python3.12-dev libpipewire-0.3-0 pipewire libxcb-cursor0 should be installed
# patchelf should be > 0.12 you can use something like this: https://github.com/NixOS/patchelf/releases/download/0.18.0/patchelf-0.18.0-x86_64.tar.gz


CC=clang-18 CXX=clang++-18 nuitka --onefile --plugin-enable=pyqt6 --show-progress plex_music_player/__main__.py || exit 1
chmod +x __main__.bin
mv __main__.bin PlexMusicPlayer_$(arch)


# To build arm64 you should run it on arm machine or use docker with arm64 architecture
# To prepare docker image run:
# docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
# docker buildx create --use --name multiarch-builder || docker buildx use multiarch-builder
# docker buildx inspect --bootstrap

# Then you can build it with:
# docker buildx build --platform linux/arm64 -t plexmusicplayer:latest .
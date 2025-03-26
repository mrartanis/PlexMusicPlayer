pyinstaller -F --add-data "MusicApp.iconset/icon_256x256.png:icon" plex_music_player/__main__.py || exit 1
mv dist/__main__ PlexMusicPlayer_linux_x86_64


# To build arm64 you should run it on arm machine or use docker with arm64 architecture
# To prepare docker image run:
# docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
# docker buildx create --use --name multiarch-builder || docker buildx use multiarch-builder
# docker buildx inspect --bootstrap

# Then you can build it with:

# QEMU_IOTHREADS=4 QEMU_IOTHREAD_POOL_SIZE=1024 QEMU_AIO=native QEMU_DRIVE_TYPE="virtio" QEMU_DRIVE_OPTS="cache=unsafe" QEMU_CPU=max QEMU_SMP=8 docker buildx build --platform linux/arm64 -t plexmusicplayer:latest --output type=local,dest=./output . 2>&1 | tee build.log
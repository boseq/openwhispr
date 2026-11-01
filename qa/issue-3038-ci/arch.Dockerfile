FROM archlinux:base
RUN pacman -Syu --noconfirm && pacman -S --noconfirm \
    python nodejs curl glibc gtk3 nss alsa-lib libxss libxshmfence libxkbfile \
    libpulse mesa libdrm libnotify libsecret libxtst xdg-utils xorg-server-xvfb xorg-xauth dbus scrot gdb binutils \
    squashfs-tools && pacman -Scc --noconfirm
ENV ELECTRON_DISABLE_SANDBOX=1

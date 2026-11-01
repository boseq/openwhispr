FROM archlinux:base
RUN pacman -Syu --noconfirm dbus gtk3 nss alsa-lib libxss libxkbfile mesa libpulse pipewire nodejs python xorg-server-xvfb xorg-xauth scrot

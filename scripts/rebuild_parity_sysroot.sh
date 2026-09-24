#!/bin/bash
# rebuild_parity_sysroot.sh — restore the cargo-gate sysroot after a sandbox
# reset (rebuild #3, 2026-09-24). The recipe: apt-get download (no root) +
# dpkg-deb -x into /home/z/parity-lab/sysroot; cargo gates on Flauz.app need
# these pkg-config entries: pipewire spa drm gbm alsa xkbcommon udev dbus
# seat wayland x11 egl gl gles glx xext xrender xfixes xcursor xrandr xi
# xinerama xcb + libclang (bindgen). Toolchain: rustup 1.97.1 (repo pin,
# rust-toolchain.toml) — reinstall separately if ~/.cargo was wiped:
#   curl -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain 1.97.1 \
#     --profile minimal --component clippy,rustfmt
set -e
mkdir -p /home/z/parity-lab/debs /home/z/parity-lab/sysroot
cd /home/z/parity-lab/debs
PKGS="libpipewire-0.3-dev libpipewire-0.3-0t64 libspa-0.2-dev libspa-0.2-modules
libdrm-dev libdrm2 libgbm-dev libgbm1 libasound2-dev libasound2t64
libxkbcommon-dev libxkbcommon0 libudev-dev libudev1 libdbus-1-dev libdbus-1-3
libseat-dev libseat1 libwayland-dev libwayland-client0 libwayland-cursor0 libwayland-egl1
libegl1 libegl-dev libgl1 libgl-dev libgles2 libgles-dev libglx0 libglx-dev
libx11-dev libx11-xcb-dev libxcb1-dev libxcb-render0-dev libxcb-shape0-dev libxcb-xfixes0-dev
libxcursor-dev libxrandr-dev libxi-dev libxinerama-dev
libxext-dev libxrender-dev libxfixes-dev x11proto-dev x11proto-input-dev
libclang1-19 libclang-common-19-dev"
# download what's missing (idempotent-ish; existing debs are skipped by name)
for p in $PKGS; do ls "${p}"_*.deb >/dev/null 2>&1 || apt-get download "$p" || echo "WARN: $p unavailable"; done
cd /home/z/parity-lab/sysroot
for d in ../debs/*.deb; do dpkg-deb -x "$d" .; done
echo "sysroot rebuilt — source /home/z/parity-lab/build_env.sh before cargo"

# parity-lab build environment (rebuild #3 after sandbox reset 2026-09-24;
# original recipe: worklog line 538/573). Source before any cargo gate run.
export SYSROOT_DIR=/home/z/parity-lab/sysroot
export PKG_CONFIG_PATH="$SYSROOT_DIR/usr/lib/x86_64-linux-gnu/pkgconfig:$SYSROOT_DIR/usr/share/pkgconfig:$SYSROOT_DIR/usr/lib/pkgconfig"
export PKG_CONFIG_SYSROOT_DIR="$SYSROOT_DIR"
export PKG_CONFIG_ALLOW_SYSTEM_CFLAGS=1
export LIBCLANG_PATH="$SYSROOT_DIR/usr/lib/llvm-19/lib"
export BINDGEN_EXTRA_CLANG_ARGS="-I$SYSROOT_DIR/usr/lib/llvm-19/lib/clang/19/include -I$SYSROOT_DIR/usr/include"
export LD_LIBRARY_PATH="$SYSROOT_DIR/usr/lib/x86_64-linux-gnu:$SYSROOT_DIR/usr/lib/llvm-19/lib:$LD_LIBRARY_PATH"
export CARGO_INCREMENTAL=0
export CARGO_PROFILE_DEV_DEBUG=0

#!/bin/bash
# Assembles kamakiri-arm64-update.zip: new lk-payload + injected ARM64 boot image.
# Usage: ./makedist-arm64.sh [boot-arm64-kamakiri.img]
set -euo pipefail

IMG=${1:-boot-arm64-kamakiri.img}
LK=bin/lk.bin
PINNED_LK_SHA=4da5843f7cbdb537520578e3e0d39e28110d7c2d2f812b4dbc9cbbdd348d6116
MARKER="bootopt=64S3,32N2,64N2"
OUT=kamakiri-arm64-update.zip

make -C lk-payload test
make -C lk-payload

[ -f "$IMG" ] || { echo "missing $IMG"; echo "inject first: python3 microloader/inject_microloader.py boot-arm64.img microloader/build/payload.bin $IMG"; exit 1; }
[ -f "$LK" ] || { echo "missing $LK (needed to verify the installed LK on device)"; exit 1; }

LK_SHA=$(sha256sum "$LK" | cut -d' ' -f1)
[ "$LK_SHA" = "$PINNED_LK_SHA" ] || { echo "bin/lk.bin ($LK_SHA) != pinned $PINNED_LK_SHA"; echo "g_is_64bit_kernel address is invalid for this LK; re-derive lk-payload/common.h first"; exit 1; }

LK_BLOCKS=$(( ( $(stat -c%s "$LK") + 511 ) / 512 ))

# image sanity: real header at 0x400, ARM64 marker first in cmdline at 0x440
[ "$(dd if="$IMG" bs=1 skip=1024 count=8 2>/dev/null)" = "ANDROID!" ] || { echo "bad magic at 0x400 in $IMG"; exit 1; }
[ "$(dd if="$IMG" bs=1 skip=1088 count=22 2>/dev/null)" = "$MARKER" ] || { echo "$IMG: cmdline must start with $MARKER"; exit 1; }

rm -rf dist/arm64-update
mkdir -p dist/arm64-update/arm64 dist/arm64-update/META-INF/com/google/android
cp lk-payload/build/payload.bin dist/arm64-update/arm64/payload.bin
cp "$IMG" dist/arm64-update/arm64/boot-arm64-kamakiri.img
sed -e "s/__LK_SHA256__/$LK_SHA/" -e "s/__LK_BLOCKS__/$LK_BLOCKS/" \
    arm64/META-INF/com/google/android/update-binary > dist/arm64-update/META-INF/com/google/android/update-binary
chmod 755 dist/arm64-update/META-INF/com/google/android/update-binary
cp arm64/META-INF/com/google/android/updater-script dist/arm64-update/META-INF/com/google/android/

rm -f "$OUT"
(cd dist/arm64-update && zip -qr "$OLDPWD/$OUT" .)
echo "$OUT ready ($(du -h "$OUT" | cut -f1))"

#!/bin/bash
# Build the OpenWrt GPT repartition zip from a make-gpt.sh output directory.
# Self-contained project: independent of the parent kamakiri installer.
# TWRP-flashable only. --on-device needs a static ARM32 cross compiler;
# otherwise provide a dump directory first (see GPT.md).
set -e
cd "$(dirname "$0")"

# Single system layout: cache removed; vendor and every other partition
# keep their position and size. system replaces system+userdata.
# Default build omits the current-GPT hash guard (flashes from any table
# state); --check-hash restores it (pinned original/new tables only).
CHECK_HASH=0
GENERATE=0
if [ "${1:-}" = "--on-device" ]; then GENERATE=1; shift; fi
if [ "${1:-}" = "--check-hash" ]; then CHECK_HASH=1; shift; fi
INPUT=${1:-bin/gpt-openwrt}
if [ "$GENERATE" = 1 ]; then
    [ "$CHECK_HASH" = 0 ] || { echo '--check-hash requires a source dump' >&2; exit 1; }
    python3 test_generate.py
    mkdir -p bin
    "${ARMCC:-arm-linux-gnueabihf-gcc}" -std=c99 -Os -Wall -Wextra -Werror -static -s gpt-generate.c -o bin/gpt-generate
    # Reject a host or dynamically linked binary before shipping to recovery.
    python3 - <<'PY'
from pathlib import Path
import struct
b = Path('bin/gpt-generate').read_bytes()
assert b[:7] == b'\x7fELF\x01\x01\x01' and struct.unpack_from('<HH', b, 16) == (2, 40), 'Expected ARM32 executable'
offset = struct.unpack_from('<I', b, 28)[0]
size, count = struct.unpack_from('<HH', b, 42)
assert all(struct.unpack_from('<I', b, offset + i * size)[0] != 3 for i in range(count)), 'Expected static executable'
PY
    SECTORS=0
    NAME=sheldon-gpt-on-device
else
    python3 test_gpt.py "$INPUT"
    SECTORS=$(python3 -c 'import struct, sys; from pathlib import Path; print(struct.unpack_from("<Q", (Path(sys.argv[1]) / "gpt-primary.bin").read_bytes(), 544)[0] + 1)' "$INPUT")
    NAME=sheldon-gpt-openwrt-system-$SECTORS
    [ "$CHECK_HASH" = 1 ] || NAME=$NAME-nocheck
fi
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/META-INF/com/google/android" "$STAGE/gpt" dist
if [ "$GENERATE" = 1 ]; then
    cp bin/gpt-generate "$STAGE/gpt/"
    GENERATOR_SHA=$(sha256sum bin/gpt-generate | cut -d' ' -f1)
else
    for file in gpt-primary.bin gpt-backup.bin original-primary.bin original-backup.bin layout.sfdisk original.sfdisk; do
        cp "$INPUT/$file" "$STAGE/gpt/"
    done
    GENERATOR_SHA=unused
fi
cp README.txt "$STAGE/gpt/"
sha() {
    if [ "$GENERATE" = 1 ]; then echo unused; else sha256sum "$INPUT/$1" | cut -d' ' -f1; fi
}
sed -e "s/__CHECK_HASH__/$CHECK_HASH/" \
    -e "s/__SECTORS__/$SECTORS/" \
    -e "s/__GENERATE__/$GENERATE/" \
    -e "s/__GENERATOR_SHA256__/$GENERATOR_SHA/" \
    -e "s/__PRIMARY_SHA256__/$(sha gpt-primary.bin)/g" \
    -e "s/__BACKUP_SHA256__/$(sha gpt-backup.bin)/g" \
    -e "s/__ORIGINAL_PRIMARY_SHA256__/$(sha original-primary.bin)/g" \
    -e "s/__ORIGINAL_BACKUP_SHA256__/$(sha original-backup.bin)/g" \
    META-INF/com/google/android/update-binary > "$STAGE/META-INF/com/google/android/update-binary"
chmod 755 "$STAGE/META-INF/com/google/android/update-binary"
cp META-INF/com/google/android/updater-script "$STAGE/META-INF/com/google/android/"
python3 - "$STAGE" "dist/$NAME.zip" <<'PY'
from pathlib import Path
import sys
import zipfile

stage = Path(sys.argv[1])
with zipfile.ZipFile(sys.argv[2], "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(stage.rglob("*")):
        if path.is_file():
            archive.write(path, path.relative_to(stage))
PY
rm -rf "$STAGE"; trap - EXIT
if [ "$GENERATE" = 1 ]; then
    python3 test_live.py "dist/$NAME.zip"
else
    python3 test_gpt.py "$INPUT" "dist/$NAME.zip"
fi
echo "dist/$NAME.zip ready (GPT only, no filesystems formatted)"

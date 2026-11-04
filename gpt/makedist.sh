#!/bin/bash
# Build the OpenWrt GPT repartition zip from a make-gpt.sh output directory.
# Self-contained project: independent of the parent kamakiri installer.
# TWRP-flashable only. Needs the dump directory first (see GPT.md).
set -e
cd "$(dirname "$0")"

# Single system layout: cache removed; vendor and every other partition
# keep their position and size. system replaces system+userdata.
# Default build omits the current-GPT hash guard (flashes from any table
# state); --check-hash restores it (pinned original/new tables only).
CHECK_HASH=0
if [ "${1:-}" = "--check-hash" ]; then CHECK_HASH=1; shift; fi
INPUT=${1:-bin/gpt-openwrt}

python3 test_gpt.py "$INPUT"

NAME=sheldon-gpt-openwrt-system
[ "$CHECK_HASH" = 1 ] || NAME=$NAME-nocheck
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/META-INF/com/google/android" "$STAGE/gpt" dist
for file in gpt-primary.bin gpt-backup.bin original-primary.bin original-backup.bin layout.sfdisk original.sfdisk; do
    cp "$INPUT/$file" "$STAGE/gpt/"
done
cp README.txt "$STAGE/gpt/"
sha() { sha256sum "$INPUT/$1" | cut -d' ' -f1; }
sed -e "s/__CHECK_HASH__/$CHECK_HASH/" \
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
python3 test_gpt.py "$INPUT" "dist/$NAME.zip"
echo "dist/$NAME.zip ready (GPT only, no filesystems formatted)"

#!/bin/bash
# Build a standalone TWRP GPT updater from make-gpt.sh output.
set -euo pipefail
cd "$(dirname "$0")"
INPUT=${1:-bin/gpt-openwrt-128}
[ "$#" -le 2 ] || { echo "usage: $0 [GPT_DIRECTORY [OUTPUT_ZIP]]" >&2; exit 1; }
python3 test_gpt.py "$INPUT"
if ! grep -q 'name="vendor"' "$INPUT/layout.sfdisk"; then
    NAME=sheldon-gpt-openwrt-64-no-vendor
elif grep -Eq 'size=[[:space:]]*131072,.*name="system"' "$INPUT/layout.sfdisk"; then
    NAME=sheldon-gpt-openwrt-64
else
    NAME=sheldon-gpt-openwrt-128
fi
OUT=${2:-"$PWD/dist/$NAME.zip"}

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/gpt" "$STAGE/META-INF/com/google/android"
for file in gpt-primary.bin gpt-backup.bin original-primary.bin original-backup.bin layout.sfdisk original.sfdisk; do
    cp "$INPUT/$file" "$STAGE/gpt/"
done
cp gpt/README.txt "$STAGE/gpt/"
sha() { sha256sum "$INPUT/$1" | cut -d' ' -f1; }
sed -e "s/__PRIMARY_SHA256__/$(sha gpt-primary.bin)/g" \
    -e "s/__BACKUP_SHA256__/$(sha gpt-backup.bin)/g" \
    -e "s/__ORIGINAL_PRIMARY_SHA256__/$(sha original-primary.bin)/g" \
    -e "s/__ORIGINAL_BACKUP_SHA256__/$(sha original-backup.bin)/g" \
    gpt/META-INF/com/google/android/update-binary > "$STAGE/META-INF/com/google/android/update-binary"
chmod 755 "$STAGE/META-INF/com/google/android/update-binary"
cp gpt/META-INF/com/google/android/updater-script "$STAGE/META-INF/com/google/android/"
(cd "$STAGE" && zip -qr "$STAGE/update.zip" META-INF gpt)
python3 package_bootrom.py gpt "$STAGE/update.zip" "$INPUT"
python3 test_gpt.py "$INPUT" "$STAGE/update.zip"
mkdir -p "$(dirname "$OUT")"
mv "$STAGE/update.zip" "$OUT"
printf '%s ready (GPT only, no filesystems formatted)\n' "$OUT"

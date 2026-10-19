#!/bin/bash
# Build the OpenWrt GPT repartition zip from a make-gpt.sh output directory.
# Self-contained project: independent of the parent kamakiri installer.
# TWRP-flashable only. Needs the dump directory first (see GPT.md).
set -e
cd "$(dirname "$0")"

INPUT=${1:-bin/gpt-openwrt-128}
python3 test_gpt.py "$INPUT"
if ! grep -q 'name="vendor"' "$INPUT/layout.sfdisk"; then
    NAME=sheldon-gpt-openwrt-64-no-vendor
elif grep -Eq 'size=[[:space:]]*131072,.*name="system"' "$INPUT/layout.sfdisk"; then
    NAME=sheldon-gpt-openwrt-64
else
    NAME=sheldon-gpt-openwrt-128
fi
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/META-INF/com/google/android" "$STAGE/gpt" dist
for file in gpt-primary.bin gpt-backup.bin original-primary.bin original-backup.bin layout.sfdisk original.sfdisk; do
    cp "$INPUT/$file" "$STAGE/gpt/"
done
cp README.txt "$STAGE/gpt/"
sha() { sha256sum "$INPUT/$1" | cut -d' ' -f1; }
sed -e "s/__PRIMARY_SHA256__/$(sha gpt-primary.bin)/g" \
    -e "s/__BACKUP_SHA256__/$(sha gpt-backup.bin)/g" \
    -e "s/__ORIGINAL_PRIMARY_SHA256__/$(sha original-primary.bin)/g" \
    -e "s/__ORIGINAL_BACKUP_SHA256__/$(sha original-backup.bin)/g" \
    META-INF/com/google/android/update-binary > "$STAGE/META-INF/com/google/android/update-binary"
chmod 755 "$STAGE/META-INF/com/google/android/update-binary"
cp META-INF/com/google/android/updater-script "$STAGE/META-INF/com/google/android/"
( cd "$STAGE" && zip -qr "$OLDPWD/dist/$NAME.zip" META-INF gpt )
rm -rf "$STAGE"; trap - EXIT
python3 test_gpt.py "$INPUT" "dist/$NAME.zip"
echo "dist/$NAME.zip ready (GPT only, no filesystems formatted)"

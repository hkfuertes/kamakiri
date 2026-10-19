#!/bin/bash
# Build the OpenWrt GPT repartition zip from a make-gpt.sh output directory.
# Self-contained project: independent of the parent kamakiri installer.
# TWRP-flashable only. Needs the dump directory first (see GPT.md).
set -e
cd "$(dirname "$0")"

# System partition size in MiB. Cache is always removed; vendor and every
# other partition keep their position and size. The zip is named after it.
SYSTEM_MIB=${1:-64}
INPUT=${2:-bin/gpt-openwrt}

python3 test_gpt.py "$INPUT"
size=$(sed -n 's/.*start= *409600, size= *\([0-9]*\), .*name="system".*/\1/p' "$INPUT/layout.sfdisk")
[ "$((size / 2048))" = "$SYSTEM_MIB" ] ||
    { echo "$INPUT has a $((size / 2048)) MiB system; pass that as the first argument" >&2; exit 1; }

NAME=sheldon-gpt-openwrt-$SYSTEM_MIB
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

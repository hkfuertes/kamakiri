#!/bin/sh
# Run on Sheldon/OpenWrt: sh make-gpt.sh /tmp/gpt-openwrt
# Optional first argument: system partition size in MiB (default 64).
# One layout: cache removed; vendor and every other partition keep their
# position, size and GUID; userdata extends to the last LBA.
# Generates files only. Never writes the eMMC or formats userdata.
set -eu

SYSTEM_MIB=64
case "${1:-}" in
    '') ;;
    *[!0-9]*) ;;
    *) SYSTEM_MIB=$1; shift ;;
esac
[ "$#" -eq 1 ] || { echo "usage: sh $0 [SYSTEM_MIB] NEW_OUTPUT_DIRECTORY" >&2; exit 1; }
[ "$SYSTEM_MIB" -gt 0 ] || { echo "system size must be a positive MiB count" >&2; exit 1; }
command -v sfdisk >/dev/null
OUT=$1
DEV=/dev/mmcblk0
read -r SECTORS < /sys/class/block/mmcblk0/size
read -r SECTOR_SIZE < /sys/class/block/mmcblk0/queue/logical_block_size
[ "$SECTORS" = 15273600 ] && [ "$SECTOR_SIZE" = 512 ] || {
    echo "Unexpected eMMC geometry; refusing to generate GPT" >&2; exit 1;
}

mkdir "$OUT" # Refuse to overwrite an existing directory.
IMAGE=$OUT/disk.img
trap 'rm -f "$IMAGE"' 0
trap 'exit 1' HUP INT TERM

dd if="$DEV" of="$OUT/original-primary.bin" bs=512 count=34
dd if="$DEV" of="$OUT/original-backup.bin" bs=512 skip=$((SECTORS - 33)) count=33
ACTUAL=$(dd if="$OUT/original-primary.bin" bs=512 skip=2 count=32 | sha256sum | awk '{print $1}')
case "$ACTUAL" in
    25aea305a221daf2204d7ca7f0d1af571d4944b272c450cbe36a0e9d99a5d26a|\
    fd41582e245a85b5af06bf2880c144086ad7b0180daf743492ab1a1f08cc0acd|\
    d48e33830e03104aa1e7e5ffa56d04dce459df19b43881b60040a4125fa8f305|\
    e0a0559a4e53c781a14c6bebced30da759184e2ffb4f290bcd110ffa9a0b3c65|\
    7ca3a6adf5b39bf21bb0fe2e359454b4eff02221cae0053fd868625a0df8cd8c|\
    689a53584c374ca2f4efebc568396f221cea95cab8857c749bd8ddf2c653b568|\
    6cec64797a3a22e125fdd06c871a2f009a4209b3c7c61104b82a8e68c9c3cf93) ;;
    *) echo "Unexpected source GPT; refusing to generate" >&2; exit 1 ;;
esac
sfdisk --dump "$DEV" > "$OUT/original.sfdisk"
# A reinstallation may change GUIDs; retain identifiers from the verified source.
guid() {
    value=$(sed -n "s/.*uuid=\([^,]*\),.*name=\"$1\".*/\1/p" "$OUT/original.sfdisk")
    printf '%s\n' "${value:-INVALID}"
}
DISK_GUID=$(awk '/^label-id:/ {print $2}' "$OUT/original.sfdisk")

definition() {
    SYSTEM_START=409600
    SYSTEM_SIZE=$(( ${1:-$SYSTEM_MIB} * 2048 ))
    USERDATA_START=$((SYSTEM_START + SYSTEM_SIZE))
    USERDATA_SIZE=$((15273567 - USERDATA_START))
    cat <<GPT
label: gpt
label-id: ${DISK_GUID:-INVALID}
unit: sectors
first-lba: 34
last-lba: 15273566
sector-size: 512

start=1024, size=2048, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, uuid=$(guid lk), name="lk"
start=3072, size=10240, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, uuid=$(guid tee1), name="tee1"
start=13312, size=10240, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, uuid=$(guid tee2), name="tee2"
start=23552, size=32768, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, uuid=$(guid boot), name="boot"
start=56320, size=32768, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, uuid=$(guid recovery), name="recovery"
start=89088, size=7168, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, uuid=$(guid logo), name="logo"
start=96256, size=2048, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, uuid=$(guid kb), name="kb"
start=98304, size=2048, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, uuid=$(guid dkb), name="dkb"
start=100352, size=2048, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, uuid=$(guid MISC), name="MISC"
start=102400, size=307200, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, uuid=$(guid vendor), name="vendor"
start=$SYSTEM_START, size=$SYSTEM_SIZE, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, uuid=$(guid system), name="system"
start=$USERDATA_START, size=$USERDATA_SIZE, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, uuid=$(guid userdata), name="userdata"
GPT
}

# A sparse regular file: only the GPT sectors consume space, not the full 8 GB.
dd if=/dev/zero of="$IMAGE" bs=512 seek=$((SECTORS - 1)) count=1
# Create a NEW GPT on the blank file from the complete layout; no resizing/reordering.
definition > "$OUT/definition.sfdisk"
sfdisk --wipe never --wipe-partitions never "$IMAGE" < "$OUT/definition.sfdisk"
# sfdisk normalizes the protective MBR size; retain the original sector exactly.
dd if="$OUT/original-primary.bin" of="$IMAGE" bs=512 count=1 conv=notrunc
sfdisk --verify "$IMAGE"
sfdisk --dump "$IMAGE" > "$OUT/layout.sfdisk"
dd if="$IMAGE" of="$OUT/gpt-primary.bin" bs=512 count=34
dd if="$IMAGE" of="$OUT/gpt-backup.bin" bs=512 skip=$((SECTORS - 33)) count=33

printf '\nGenerated: %s/gpt-primary.bin (LBA 0, 34 sectors)\n' "$OUT"
printf 'Generated: %s/gpt-backup.bin (LBA %s, 33 sectors)\n' "$OUT" "$((SECTORS - 33))"
printf 'system: %s MiB (p11); vendor: retained; cache: removed; userdata: %s MiB (p12); no entry gaps\n' \
    "$SYSTEM_MIB" "$(( (15273567 - 409600 - SYSTEM_MIB * 2048) / 2048 ))"
printf 'No eMMC writes or filesystem changes performed.\n'

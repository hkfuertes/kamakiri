# Sheldon: OpenWrt GPT repartitioning (experimental)

This directory is a self-contained project inside the kamakiri monorepo: a
GPT generator plus a TWRP-flashable zip, independent of the parent kamakiri
installer. Generating the files never modifies the eMMC.

## Layout

One layout:

- `cache` is **removed**.
- `vendor` and every other partition keep their position, size and GUID.
- a single `rootfs` is p11, from LBA 409600 to the last usable LBA
  (7257.796 MiB); it replaces `system` and `userdata`.

Entries are consecutive, no gaps. Labels and GUIDs are preserved; mounts
must use labels, not partition numbers.

The OTA `vendor` partition contains Android HAL/libraries, Android kernel
modules and firmware, including `WIFI_RAM_CODE_MT7663.bin`,
`mt7663_patch_e2_hdr.bin` and `EEPROM_MT7663.bin`. It stays intact; if a
mainline driver ever needs one of those blobs, package it in the rootfs.

Step keeps the current dependencies: `lk`, `boot`, `recovery` and `MISC`
are looked up by name among the first 16 GPT entries, 128 bytes each from
LBA 2; the installer also requires `tee1`. Dropping `recovery` would
require adapting the boot flow, the MISC flags and the installers.

## Generating the GPT (on the device)

`make-gpt.sh` runs on OpenWrt with `sfdisk` already installed. It is
pinned to the GPT read from this stick and to its 15273600-sector /
512-byte eMMC; it only accepts verified tables (pinned SHA256 allowlist)
and takes the GUIDs from the original dump. Binaries and installers are
pinned to the GUID profile used to build them; after restoring another
GPT, regenerate the files and review the hashes. It builds a GPT **from
scratch**, with a complete 11-partition definition, over an empty sparse
file: it does not resize or reorder a previous table. It keeps the
original MBR, never writes the eMMC and requires a fresh output directory:

```sh
ssh root@192.168.1.1 'sh -s -- /tmp/gpt-openwrt' < make-gpt.sh
mkdir -p bin
scp -O -r root@192.168.1.1:/tmp/gpt-openwrt bin/
./makedist.sh
```

All commands run from this `gpt/` directory. The files land in
`bin/gpt-openwrt/`:

- `gpt-primary.bin`: 34 sectors, from LBA 0 (includes the original MBR).
- `gpt-backup.bin`: 33 sectors, from LBA 15273567.
- `original-primary.bin` and `original-backup.bin`: previous copies.
- `layout.sfdisk`: description of the new table.

## Packaging and flashing

`./makedist.sh [--check-hash] [INPUT_DIR]` validates the input with
`test_gpt.py`, stages the data, fills the SHA256 guards in the installer,
zips and re-validates. By default the installer does NOT pin the device's
current GPT to the original/new tables (it flashes from any table state);
`--check-hash` restores that guard. Output:
`dist/sheldon-gpt-openwrt-rootfs-nocheck.zip` (default) or
`dist/sheldon-gpt-openwrt-rootfs.zip` (`--check-hash`).
It installs no LK, preloader or partition images; it does not run the full
kamakiri installer. It checks device, geometry, file hashes and both
current tables; it writes the backup first, verifies the readback, then
writes and verifies the primary. It refuses to proceed with affected
partitions mounted and never formats. TWRP extracts exact entry names
(its `unzip` does not expand globs) and uses `toybox dd`: the standalone
`dd` in this recovery does not support the end-of-eMMC offsets.

**In TWRP:** the installer unmounts System, Cache, Vendor and Data itself
and aborts without writing if a mount cannot be released; use USB or ADB
sideload if the zip was stored on Data. After flashing, **reboot recovery
before formatting or writing `rootfs`**: the kernel may still be using the
old map. The stock `userdata` ext4 still sits inside the new rootfs
extent; writing the rootfs image replaces it.

Reproducible host-side check, including a simulation of the installer over
a sparse file (no real devices):

```sh
python3 test_gpt.py bin/gpt-openwrt dist/sheldon-gpt-openwrt-rootfs.zip
```

## Manual flashing with `dd`

**Only from TWRP or an initramfs, with `system`, `cache` and `userdata`
unmounted.** Do not run this from the installed OpenWrt, which uses `/rom`
and `/overlay` on the eMMC. This procedure requires the original GPT; if a
comparison fails, stop.

From the host, with TWRP booted and ADB connected:

```sh
python3 test_gpt.py bin/gpt-openwrt
adb push bin/gpt-openwrt/*.bin /tmp/
adb shell
```

In the TWRP shell (in a Linux initramfs, change `DEV` to `/dev/mmcblk0`):

```sh
set -eu
cd /tmp
DEV=/dev/block/mmcblk0
command -v toybox >/dev/null # Needed for 64-bit offsets in TWRP.
[ -b "$DEV" ]
read -r sectors < /sys/class/block/mmcblk0/size
read -r sector_size < /sys/class/block/mmcblk0/queue/logical_block_size
[ "$sectors" = 15273600 ] && [ "$sector_size" = 512 ] || exit 1
for part in 11 12 13; do
    node=/sys/class/block/mmcblk0p$part/dev
    if [ ! -f "$node" ]; then
        case "$part" in 12|13) continue ;; esac
        exit 1
    fi
    read -r devnum < "$node"
    mounted=$(awk -v n="$devnum" '$3 == n || $5 ~ /^\/(data|cache|system|system_root|rom|overlay)(\/|$)/ { print $5; exit }' /proc/self/mountinfo)
    [ -z "$mounted" ] || { echo "Unmount: $mounted"; exit 1; }
done

toybox dd if="$DEV" of=before-primary.bin bs=512 count=34
toybox dd if="$DEV" of=before-backup.bin bs=512 skip=15273567 count=33
cmp original-primary.bin before-primary.bin
cmp original-backup.bin before-backup.bin

# Backup first; do not touch the primary if its write or verification fails.
toybox dd if=gpt-backup.bin of="$DEV" bs=512 seek=15273567 count=33 conv=notrunc
sync
toybox dd if="$DEV" of=check-backup.bin bs=512 skip=15273567 count=33
cmp gpt-backup.bin check-backup.bin

toybox dd if=gpt-primary.bin of="$DEV" bs=512 count=34 conv=notrunc
sync
toybox dd if="$DEV" of=check-primary.bin bs=512 count=34
cmp gpt-primary.bin check-primary.bin
```

The target is **the whole eMMC disk**, never `mmcblk0boot0` or a
`mmcblk0pN` partition. Afterwards, **reboot recovery before writing the
rootfs image**. No filesystem is formatted or moved by these commands.

Going back to Android will require restoring the GPT and the Android
images, plus Kamakiri: reinstalling Kamakiri alone does not rebuild the
deleted data.

## Relation to the ARM64 payload

The GPT zip is independent: `dist/sheldon-gpt-openwrt-rootfs.zip` (TWRP). If
you use both, update the payload first, then the GPT, and **reboot recovery
before writing the rootfs**.

The payload update is documented in [../ARM64.md](../ARM64.md).

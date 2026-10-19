# Sheldon: OpenWrt GPT repartitioning (experimental)

This directory is a self-contained project inside the kamakiri monorepo: a
GPT generator plus a TWRP-flashable zip, independent of the parent kamakiri
installer. Generating the files never modifies the eMMC.

Agreed order:

1. **ARM64 as-is.** Test with the current partitioning and boot firmware.
   Only the payload and the boot image change; names and sizes are kept.
2. **Reclaim space without touching `vendor` or the rescue partitions.**
   Shrink `system` (`/rom`) to **128 MiB**, drop `cache` and hand the space
   to `userdata` (`/overlay`): **7129.796 MiB**. `recovery` and every other
   partition keep their names, positions, sizes and GUIDs. The new GPT has
   consecutive entries: `system` is p11 and `userdata` p12, no `cache`, no
   gaps. GUIDs are preserved; mounts must use labels, not p13.
3. **Prepared vendorless variant: 64 MiB system.** `system` becomes p10,
   LBA 102400..233471; `userdata` p11, LBA 233472..15273566 (**7343.796
   MiB**). p1..p9 and the labels are kept; no gaps remain. Applying it is
   still pending validation/preservation of the needed firmware. Only once
   it has been verified that the firmware available for mainline suffices
   for the target hardware, and the required blobs/data have been preserved,
   remove `vendor` and re-adjust the layout to use its space.

The OTA `vendor` partition contains Android HAL/libraries, Android kernel
modules and firmware, including `WIFI_RAM_CODE_MT7663.bin`,
`mt7663_patch_e2_hdr.bin` and `EEPROM_MT7663.bin`. The Android modules are
useless for mainline; whatever blobs/data their drivers need can be packaged
into the rootfs. `vendor` stays intact during steps 1 and 2; its removal is
deferred to step 3.

Step 2 keeps the current dependencies: `lk`, `boot`, `recovery` and `MISC`
are looked up by name among the first 16 GPT entries, 128 bytes each from
LBA 2; the installer also requires `tee1`. Dropping `recovery` at any other
point would require adapting the boot flow, the MISC flags and the
installers.

## Generating the GPT and the zip

`make-gpt.sh` runs on OpenWrt with `sfdisk` already installed. It is pinned
to the GPT read from this stick and to its 15273600-sector / 512-byte eMMC;
it only accepts verified tables and takes the GUIDs from the original dump.
Binaries and installers are pinned to the GUID profile used to build them;
after restoring another GPT, regenerate the files and review the hashes.
It builds a GPT **from scratch**, with a complete 12-partition definition
(11 in the vendorless variant), over an empty sparse file: it does not
resize or reorder a previous table. It keeps the original MBR, never writes
the eMMC and requires a fresh output directory:

```sh
ssh root@192.168.1.1 'sh -s -- /tmp/gpt-openwrt-128' < make-gpt.sh
mkdir -p bin
scp -O -r root@192.168.1.1:/tmp/gpt-openwrt-128 bin/
./makedist.sh
```

All commands run from this `gpt/` directory. The files land in
`bin/gpt-openwrt-128/`:

- `gpt-primary.bin`: 34 sectors, from LBA 0 (includes the original MBR).
- `gpt-backup.bin`: 33 sectors, from LBA 15273567.
- `original-primary.bin` and `original-backup.bin`: previous copies.
- `layout.sfdisk`: description of the new table.

The zip is `dist/sheldon-gpt-openwrt-128.zip`. It installs no LK, preloader
or partition images. It includes the original GPT copies; it does not run
the full kamakiri installer. It checks device, geometry, file hashes and
both current tables; it writes the backup first, verifies the readback,
then writes and verifies the primary. It refuses to proceed with affected
partitions mounted and never formats. TWRP extracts exact entry names (its
`unzip` does not expand globs) and uses `toybox dd`: the standalone `dd` in
this recovery does not support the end-of-eMMC offsets.

**In TWRP:** unmount System, Cache and Data; use USB or ADB sideload if the
zip was stored on Data. After flashing, **reboot recovery before wiping or
recreating `userdata`**: the kernel may still be using the old map. Coming
from stock, its boot changes too: changing the GPT does not move its ext4.
If you only move from the experimental p13 layout to p12 with the same
limits, no reformat is needed. The user recreates it; check its
mount/label and sysupgrade compatibility. The previous ROM observed over
UART contains `sheldon-overlay-init`, which rejects the new geometry with
`Stock geometry mismatch`. That initializer must also be adapted to the
`userdata` layout/label; generating or flashing another GPT does not remove
that check.

Reproducible host-side check, including a simulation of the installer over
a sparse file (no real devices):

```sh
python3 test_gpt.py bin/gpt-openwrt-128 dist/sheldon-gpt-openwrt-128.zip
```

## 64 MiB vendorless variant

The previous 128 MiB with-vendor variant is kept; its binaries and zip are
not overwritten. The new one keeps the labels and retained GUIDs, but
**physically moves system and userdata**. The GPT does not move their
contents. The user-updated OpenWrt uses labels, with no dependence on UUIDs
or partition numbers.

Generate (read-only on the eMMC, writes to files) and package:

```sh
sh make-gpt.sh --no-vendor /tmp/gpt-openwrt-64-no-vendor
# Copy that directory into bin/ before packaging.
./makedist.sh bin/gpt-openwrt-64-no-vendor
python3 test_gpt.py bin/gpt-openwrt-64-no-vendor dist/sheldon-gpt-openwrt-64-no-vendor.zip
```

Output: `bin/gpt-openwrt-64-no-vendor/{gpt-primary,gpt-backup}.bin` and
`dist/sheldon-gpt-openwrt-64-no-vendor.zip` (TWRP).
After flashing, **reboot recovery before writing images or recreating
Data**; reflash the OpenWrt system (at most **67108864 bytes**) and
recreate userdata. The rootfs must carry the needed firmware: it can no
longer come from vendor.

## 64 MiB with-vendor variant

Keeps p1..p10, including the 150 MiB vendor in its original position.
System is p11, LBA 409600..540671 (64 MiB); userdata is p12, LBA
540672..15273566 (7193.796 MiB). Cache stays removed. Labels, GUIDs and
consecutive entries are preserved, without overwriting the other variants.

```sh
sh make-gpt.sh --64 /tmp/gpt-openwrt-64
# Copy into bin/ before packaging.
./makedist.sh bin/gpt-openwrt-64
python3 test_gpt.py bin/gpt-openwrt-64 dist/sheldon-gpt-openwrt-64.zip
```

Coming from the vendorless variant, system goes back from 50 to 200 MiB:
the GPT does not move the rootfs or restore overwritten vendor data.
Reboot recovery before writing images or recreating userdata; the system
image must fit in 67108864 bytes. An original vendor copy exists in
`bin/gpt-before-64-no-vendor-20261017-221330/vendor.img` (150 MiB), its
SHA256 verified against the previous manifest. Restoring that image is an
operation separate from GPT flashing. This variant allows investigating
the LK dependency, but it also changes the start of system: a correct boot
would not by itself prove that vendor was the cause of the failure.

## Manual flashing with `dd`

**Only from TWRP or an initramfs, with `system`, `cache` and `userdata`
unmounted.** Do not run this from the installed OpenWrt, which uses `/rom`
and `/overlay` on the eMMC. This procedure requires the original GPT; if a
comparison fails, stop.

From the host, with TWRP booted and ADB connected:

```sh
python3 test_gpt.py bin/gpt-openwrt-128
adb push bin/gpt-openwrt-128/*.bin /tmp/
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
`mmcblk0pN` partition. Afterwards, **reboot recovery before recreating
`userdata`**. No filesystem is formatted or moved by these commands.

Going back to Android will require restoring the GPT and the Android
images, plus Kamakiri: reinstalling Kamakiri alone does not rebuild the
deleted data.

## Relation to the ARM64 payload

The GPT zip is independent: `dist/sheldon-gpt-openwrt-128.zip` (TWRP). If
you use both, update the payload first, then the GPT, and **reboot recovery
before recreating userdata**.

The payload update is documented in [../ARM64.md](../ARM64.md).

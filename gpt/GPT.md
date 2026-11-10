# Sheldon: OpenWrt GPT repartitioning (experimental)

This directory is a self-contained project inside the kamakiri monorepo: a
GPT generator plus a TWRP-flashable zip, independent of the parent kamakiri
installer. Generating the files never modifies the eMMC.

## Layout

One layout:

- `cache` is **removed**.
- p1..p10, including `vendor`, keep their position, size and GUID.
- a single `system` is p11, from LBA 409600 to the last usable LBA
  (7255.984 MiB on the 15269888-sector eMMC, 7257.796 MiB on the
  15273600-sector eMMC); it replaces the old `system` and `userdata`.
  The name `system` is required by LK; do not rename it to `rootfs`.

Entries are consecutive, no gaps. Labels and GUIDs are preserved; mounts
must use labels, not partition numbers.

The OTA `vendor` partition contains Android HAL/libraries, Android kernel
modules and firmware, including `WIFI_RAM_CODE_MT7663.bin`,
`mt7663_patch_e2_hdr.bin` and `EEPROM_MT7663.bin`. It stays intact; if a
mainline driver ever needs one of those blobs, package it in the system.

Step keeps the current dependencies: `lk`, `boot`, `recovery` and `MISC`
are looked up by name among the first 16 GPT entries, 128 bytes each from
LBA 2; the installer also requires `tee1`. Dropping `recovery` would
require adapting the boot flow, the MISC flags and the installers.

## Generate and install directly in TWRP

`dist/sheldon-gpt-on-device.zip` contains a static ARM32 generator, not
prebuilt GPT tables. It reads the actual eMMC geometry and both GPT copies,
validates their headers, CRCs, matching entries and the original-13 or
already-repartitioned-11 layout, then generates both new tables in RAM.
Disk/partition GUIDs, MBR and p1..p10 are retained; `system` extends to the
last usable sector of that particular eMMC. Supported capacities are
15269888 and 15273600 sectors, with 512-byte sectors; other layouts or
capacities fail closed. The installer uses the same mount checks,
backup-first writes and readback verification as the prebuilt ZIP.

Build on a host with Python 3, a native C compiler and a static ARM32 Linux
cross-toolchain (for example `gcc-arm-linux-gnueabihf` plus its libc headers):

```sh
cd gpt
./makedist.sh --on-device
# Override ARMCC if the cross compiler has another name.
```

Install the ZIP from RAM/USB, never from a partition being removed:

```sh
adb push dist/sheldon-gpt-on-device.zip /tmp/
adb shell twrp install /tmp/sheldon-gpt-on-device.zip
```

Before writing, the installer saves the old GPT copies in a printed
`/tmp/gpt-before.XXXXXX` directory. **This backup is RAM-only**: use
`adb pull /tmp/gpt-before.XXXXXX` to keep it on the host **before rebooting**.
Keep a separate backup of any partition contents you need; GPT backups do
not preserve filesystems. Then reboot recovery before using the new map.
Nothing is formatted and LK/boot/preloader are not written by this updater.

Checks (no devices): `python3 test_generate.py` and
`python3 test_live.py dist/sheldon-gpt-on-device.zip`. The latter runs the
real shell installer against sparse files for both capacities using a host
build of the generator. The actual static ARM32 generator has also passed
both geometries under QEMU. The on-device-generation ZIP was hardware-tested
on Sheldon `G071CQ1560161WEV` (15273600 sectors): TWRP updater RC=0, exported
original backups matched the host backups, both written GPT copies matched
the independently generated expected pair, and recovery rebooted with the
new p11 map. The 15269888-sector runtime path remains host/QEMU-tested only;
its capacity-specific ZIP has been hardware-tested.

## Generating a prebuilt GPT (on OpenWrt)

`make-gpt.sh` runs on OpenWrt with `sfdisk` already installed. It is
pinned to the GPT read from this stick and to the verified 15269888- or 15273600-sector /
512-byte eMMCs; it only accepts verified tables (pinned SHA256 allowlist)
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
./makedist.sh --check-hash
```

All commands run from this `gpt/` directory. The files land in
`bin/gpt-openwrt/`:

- `gpt-primary.bin`: 34 sectors, from LBA 0 (includes the original MBR).
- `gpt-backup.bin`: 33 sectors, from LBA `sectors - 33`.
- `original-primary.bin` and `original-backup.bin`: previous copies.
- `layout.sfdisk`: description of the new table.

## Packaging and flashing

`./makedist.sh [--check-hash] [INPUT_DIR]` validates the input with
`test_gpt.py`, stages the data, fills the SHA256 guards in the installer,
zips and re-validates. By default the installer does NOT pin the device's
current GPT to the original/new tables (it flashes from any table state);
`--check-hash` restores that guard. Output:
`dist/sheldon-gpt-openwrt-system-<sectors>-nocheck.zip` (default) or
`dist/sheldon-gpt-openwrt-system-<sectors>.zip` (`--check-hash`). The size is
pinned into the prebuilt installer; never flash one capacity's ZIP on the
other.
It installs no LK, preloader or partition images; it does not run the full
kamakiri installer. It checks device, geometry and payload hashes, and reads both current
GPT copies (their hashes are enforced only with `--check-hash`); it writes the backup first, verifies the readback, then
writes and verifies the primary. It refuses to proceed with affected
partitions mounted and never formats. TWRP extracts exact entry names
(its `unzip` does not expand globs) and uses `toybox dd`: the standalone
`dd` in this recovery does not support the end-of-eMMC offsets.

**In TWRP:** the installer unmounts System, Cache, Vendor and Data itself
and aborts without writing if a mount cannot be released; use USB or ADB
sideload if the zip was stored on Data. After flashing, **reboot recovery
before formatting or writing `system`**: the kernel may still be using the
old map. Old filesystem data remains inside the expanded partition until
those sectors are overwritten. Flashing an image is not a secure erase
and does not necessarily overwrite all former `userdata` sectors.

Reproducible host-side check, including a simulation of the installer over
a sparse file (no real devices):

```sh
python3 test_gpt.py bin/gpt-openwrt dist/sheldon-gpt-openwrt-system-15269888.zip
# Use 15273600 instead for a dump from the larger eMMC.
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
EXPECTED_SECTORS=15269888 # Must match the verified dump; 15273600 on the larger eMMC.
[ "$sectors" = "$EXPECTED_SECTORS" ] && [ "$sector_size" = 512 ] || exit 1
BACKUP_LBA=$((sectors - 33))
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
toybox dd if="$DEV" of=before-backup.bin bs=512 skip="$BACKUP_LBA" count=33
cmp original-primary.bin before-primary.bin
cmp original-backup.bin before-backup.bin

# Backup first; do not touch the primary if its write or verification fails.
toybox dd if=gpt-backup.bin of="$DEV" bs=512 seek="$BACKUP_LBA" count=33 conv=notrunc
sync
toybox dd if="$DEV" of=check-backup.bin bs=512 skip="$BACKUP_LBA" count=33
cmp gpt-backup.bin check-backup.bin

toybox dd if=gpt-primary.bin of="$DEV" bs=512 count=34 conv=notrunc
sync
toybox dd if="$DEV" of=check-primary.bin bs=512 count=34
cmp gpt-primary.bin check-primary.bin
```

The target is **the whole eMMC disk**, never `mmcblk0boot0` or a
`mmcblk0pN` partition. Afterwards, **reboot recovery before writing the
system image**. No filesystem is formatted or moved by these commands.

## Original layout and rollback

The versioned `original.sfdisk` records this dongle's layout immediately
before repartitioning: disk/partition GUIDs, types, labels, starts and sizes.
Its temporary `device:` paths identify the host sparse file used for the
dump, not a flashing target. It is not a universal dump for every Sheldon.

This text can reconstruct the partition layout on a correctly sized sparse
file with `sfdisk`, after adapting the device paths. It does not preserve
the original MBR bytes or partition contents, so it is not an exact binary
backup. Binary dumps are generated locally and included in generated ZIPs,
not committed; the local `.bin` dumps used for our hardware test were
subsequently deleted. The text alone is not input for `makedist.sh`.

There is **no automated restore mode or tested rollback ZIP**. The runtime
generator likewise only repartitions; it does not implement rollback. Restoring
requires separately prepared and validated original GPT copies. Use TWRP
or an initramfs with affected partitions unmounted, verify geometry and the
current layout, write and verify backup first and primary second, then
reboot recovery before using the restored map. Do not flash the text file
or pass it directly to `dd`.

Restoring GPT does not restore filesystems or erased data. If the expanded
`system` has been written/formatted, reinstall the affected Android images
and recreate data as needed. Kamakiri alone does not recover those contents;
this GPT installer does not itself change LK, boot or recovery images.

The generator accepts only source tables in its SHA256 allowlist; it is
not a general converter for arbitrary GPTs. Do not assume it can regenerate
files from the newly installed layout. Keep the source artifacts needed
for any rebuild or rollback.

## Relation to the ARM64 payload

The GPT zip is independent: `dist/sheldon-gpt-openwrt-system-<sectors>.zip` (TWRP), or the
geometry-aware `dist/sheldon-gpt-on-device.zip`. If
you use both, update the payload first, then the GPT, and **reboot recovery
before writing the system**.

The payload update is documented in [../ARM64.md](../ARM64.md).

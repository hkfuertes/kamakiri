Sheldon OpenWrt GPT: cache removed, vendor retained, system sized by parameter
(default 64 MiB); see GPT.md and layout.sfdisk.

The ZIP installs from TWRP. It does not install Kamakiri or write boot0.
Only the verified 15273600-sector Sheldon/Sheldonp eMMC is supported.
Pinned to the source dump GUIDs; rebuild/review hashes after restoring
another GPT.

sheldon-gpt-openwrt-<SYSTEM_MIB>.zip:
  p1..p10 unchanged, vendor retained, system=p11 (SYSTEM_MIB MiB, LBA
  409600), userdata=p12 to the last LBA (7193.796 MiB at the default 64).
  Entries are consecutive. Labels and retained GUIDs are preserved. Both
  GPT copies, stock originals and layout definitions are included.
  Restoring GPT does not restore data.

BACK UP YOUR DATA. Unmount Vendor, System, Cache and Data in TWRP. Install
from USB or ADB sideload, not Data. The installer checks both current GPT
copies and writes and verifies backup first, then primary. Exact ZIP
entries and Toybox dd avoid the stock TWRP unzip/32-bit-offset/disabled-
conv problems. Nothing is formatted or moved.

REBOOT RECOVERY after flashing, BEFORE formatting or writing partition
images. Then recreate userdata and reflash the OpenWrt system image sized
to fit SYSTEM_MIB. Use labels, not partition numbers/UUID assumptions.
Do not apply from installed OpenWrt while /rom or /overlay is mounted.

Independent of kamakiri-lk-payload.zip. Neither component contains U-Boot,
a new Linux kernel/rootfs or a full bootloader installation.

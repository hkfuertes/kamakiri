Sheldon OpenWrt GPT: cache removed, vendor retained, a single rootfs
partition (p11) replaces system+userdata; see GPT.md and layout.sfdisk.

The ZIP installs from TWRP. It does not install Kamakiri or write boot0.
Only the verified 15273600-sector Sheldon/Sheldonp eMMC is supported.
Pinned to the source dump GUIDs; rebuild/review hashes after restoring
another GPT.

sheldon-gpt-openwrt-rootfs.zip:
  p1..p10 unchanged, vendor retained, rootfs=p11 from LBA 409600 to the
  last LBA (7257.796 MiB).
  Entries are consecutive. Labels and retained GUIDs are preserved. Both
  GPT copies, stock originals and layout definitions are included.
  Restoring GPT does not restore data.

BACK UP YOUR DATA. The installer unmounts Vendor, System, Cache and Data by
itself and aborts without writing if a mount cannot be released. Install
from USB or ADB sideload, not Data. The installer checks both current GPT
copies and writes and verifies backup first, then primary. Exact ZIP
entries and Toybox dd avoid the stock TWRP unzip/32-bit-offset/disabled-
conv problems. Nothing is formatted or moved.

REBOOT RECOVERY after flashing, BEFORE formatting or writing partition
images. Then format rootfs and flash the OpenWrt image into it. Use
labels, not partition numbers/UUID assumptions.
Do not apply from installed OpenWrt while /rom or /overlay is mounted.

Independent of kamakiri-lk-payload.zip. Neither component contains U-Boot,
a new Linux kernel/rootfs or a full bootloader installation.

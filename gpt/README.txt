Sheldon OpenWrt GPT: three layouts; see the root README and layout.sfdisk

The ZIP installs from TWRP. It does not install Kamakiri or
write boot0. Only the verified 15273600-sector Sheldon/Sheldonp eMMC is supported.
Pinned to the source dump GUIDs; rebuild/review hashes after restoring another GPT.

sheldon-gpt-openwrt-128.zip:
  p1..p10 unchanged, vendor retained, system=p11 (128 MiB), userdata=p12.
sheldon-gpt-openwrt-64.zip:
  p1..p10 unchanged, vendor retained, system=p11 (64 MiB), userdata=p12.
  system: LBA 409600..540671; userdata: LBA 540672..15273566 (7193.796 MiB).
  Generate from a source retaining vendor: sh make-gpt.sh --64 NEW_OUTPUT_DIRECTORY.
  Returning from vendorless moves system back to 200 MiB. GPT alone does not
  restore overwritten vendor data; restore the original vendor.img separately.
sheldon-gpt-openwrt-64-no-vendor.zip:
  p1..p9 unchanged, vendor/cache removed, system=p10 (64 MiB), userdata=p11.
  system: LBA 102400..233471; userdata: LBA 233472..15273566 (7343.796 MiB).
  System's physical start changes: the old rootfs is NOT moved by this update.

Entries are consecutive. Labels and retained GUIDs are preserved. Both GPT copies,
stock originals and layout definitions are included. Restoring GPT does not restore
data. Keep needed vendor firmware/calibration elsewhere before removing vendor.

BACK UP YOUR DATA. Unmount Vendor, System, Cache and Data in TWRP. Install from USB
or ADB sideload, not Data. The installer checks both current GPT copies and writes
and verifies backup first, then primary. Exact ZIP entries and Toybox dd avoid the
stock TWRP unzip/32-bit-offset/disabled-conv problems. Nothing is formatted or moved.

REBOOT RECOVERY after flashing, BEFORE formatting or writing partition images.
Then recreate userdata and, for the vendorless layout, reflash OpenWrt system.
The system image must fit 64 MiB (67108864 bytes) for either 64 MiB variant.
TWRP accepts the packaged original or target GPT. This does not repair
filesystem data.
Use labels, not partition numbers/UUID assumptions. OpenWrt must include its own
required firmware; /vendor is no longer available in the vendorless variant.
Do not apply from installed OpenWrt while /rom or /overlay is mounted.

Independent of kamakiri-arm64-payload.zip. Neither component contains U-Boot,
a new Linux kernel/rootfs or a full bootloader installation.

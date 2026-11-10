Sheldon GPT: cache removed, vendor retained, single system partition
(p11) replaces system+userdata. p1..p10, their GUIDs and the MBR retained.
No filesystem is formatted. The updater does not write LK, boot or boot0.

Supported eMMC: 15269888 or 15273600 sectors, 512 bytes/sector.
System starts at LBA 409600 and ends at the device's last usable LBA:
7255.984 MiB on the small eMMC, 7257.796 MiB on the large one.

sheldon-gpt-openwrt-system-<sectors>[-nocheck].zip:
Prebuilt GPT for ONE specific capacity. --check-hash restricts the current
GPT to the source dump or the generated table. Default skips that hash
guard, but still checks product, geometry and mounts. Dumps are included.

sheldon-gpt-on-device.zip:
Static ARM32 generator validates both current GPT copies and a verified
original-13 or generated-11 partition layout, then generates a native-size
GPT in TWRP. Supports per-device GUIDs, rejects other layouts/capacities.
Original GPT copies are saved to the printed /tmp/gpt-before.XXXXXX path.
RAM ONLY: adb pull that directory BEFORE rebooting to retain the backup.
Host simulation and ARM32/QEMU tested for both capacities. Runtime ZIP
hardware-tested on 15273600-sector Sheldon: RC=0, exact GPT readback and
recovery reboot. Small-capacity runtime path not yet hardware-tested.

Install through TWRP from /tmp or USB, not system/data/cache. Keep backups
of partition contents: restoring GPT alone does NOT restore data. Reboot
RECOVERY after installation before using or formatting the new partition.
See GPT.md for build commands, validation and rollback limitations.

Kamakiri Sheldon ARM32/ARM64 selector update

For Sheldon/Sheldonp with Kamakiri ALREADY installed. TWRP is only required
for the recovery method; BootROM does not need TWRP. This is not a full
Kamakiri installer and does not turn a stock kernel into an ARM64 kernel.
The payload itself remains ARM32 and selects LK's ARM64 path when the REAL
Android boot header cmdline starts with bootopt=64S3,32N2,64N2.
New boot/recovery images still need the Kamakiri microloader prefix; clean
images loaded directly by stock LK fail authentication. See ARM64.md.

Two alternative methods: flash this ZIP from TWRP, OR unzip into its own
folder and run sudo ./boot0-bootrom-flash.sh --crash on Linux with Python 3,
pyserial, pyusb and libusb installed. Start before connecting the stick.
--crash attempts the original RAM-only preloader-to-BROM transition and checks
BROM again before proceeding. Without --crash, direct BootROM is required.
Both verify LK and update only boot0 payload slots at LBAs 4096 and 1024
(backup first), checking each readback. BootROM saves the original regions
under bin/boot0-before-brom-*/ and restores eMMC user-area access on errors.
TWRP restores the previous force_ro setting. The preloader is never changed.
A full boot0 backup is saved under /tmp/kamakiri-boot0-backup.*/boot0.bin;
ADB pull that directory BEFORE rebooting if you want to keep it.

The payload-only ZIP does NOT write boot, recovery, GPT, TZ, LK or RPMB.
An optional boot image is written only by the separately built
kamakiri-arm64-update.zip; it is backed up first in the same directory.
No U-Boot, preloader, LK or TZ image is included. No partitions are formatted.
Do not use bootrom-step.sh/fixgpt as a substitute: those run the full installer.

The ARM64 selector covers normal boot/recovery, not the fastboot boot command.
AArch64 Linux boot has been observed; SMP/PSCI are not validated by this ZIP.

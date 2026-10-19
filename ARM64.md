# Sheldon: one payload for ARM32 and ARM64 kernels

The Kamakiri payload stays ARM32; the same binary lets LK boot either
kernel bitness, decided per boot image. `makedist.sh` ships it unchanged.

## Opt-in

A real Android boot header selects ARM64 when its cmdline starts with:

```text
bootopt=64S3,32N2,64N2
```

It must be the first argument, followed by end-of-string, space or tab.
Everything else — stock kernel, TWRP — stays ARM32. Covers `boot` and
`recovery` only, not `fastboot boot`. Bitness is declared in the header,
not detected from kernel contents (LK picks the load path before
decompression). Don't touch the fake header in `inject_microloader.py`.

## Compatibility

- Pinned to Kamakiri's Sheldon LK (318880 bytes, SHA256
  `4da5843f7cbdb537520578e3e0d39e28110d7c2d2f812b4dbc9cbbdd348d6116`);
  all payload addresses are specific to it. Don't substitute an OTA LK.
- ARM64 image: legacy Android header (2048-byte pages), AArch64 `Image.gz`
  + DTB, first argument as above, kernel placement per the
  [ARM64 boot protocol](https://docs.kernel.org/arch/arm64/booting.html);
  avoid overlapping LK (`0x41e00000..0x41f00000`), the payload
  (`0x41000000..0x41080000`) and staging (`0x45000000`).
- OpenWrt AArch64 seen booting with `maxcpus=1`; SMP and peripherals
  unvalidated.

## Test

```sh
make -C lk-payload test
```

Host-only selector test: opt-in, ARM32 fallback, token and buffer bounds.
No hardware.

## Original build

Kamakiri build with all partitions (Fire TV Stick 3 / Lite, Sheldon):
<https://xdaforums.com/t/unlock-root-twrp-unbrick-fire-tv-stick-3-and-fire-tv-stick-lite-sheldon-p.4410297/>

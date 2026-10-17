#!/usr/bin/env python3
"""Update only Kamakiri's boot0 payload slots; leave all boot firmware intact."""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile
import time

from common import Device
from functions import check_modemmanager
from load_payload import load_payload
from logger import log

ROOT = Path(__file__).resolve().parent.parent
# ponytail: pin the tested payload/LK pair; review hashes after code/compiler changes.
PAYLOAD_SHA = "73f3198df35204d676521e7a685ab4000b50c90a7bbc921065d5c714069f50bb"
LK_SHA = "4da5843f7cbdb537520578e3e0d39e28110d7c2d2f812b4dbc9cbbdd348d6116"
LK_SIZE = 318880
SLOTS = (4096, 1024)  # Backup first, primary only after backup readback succeeds.


def validate_payload(data):
    if not 0 < len(data) <= 0x80000:
        raise RuntimeError("Invalid payload size; no writes performed")
    data += bytes(-len(data) % 512)
    if hashlib.sha256(data).hexdigest() != PAYLOAD_SHA:
        raise RuntimeError("Unknown/corrupt payload; no writes performed")
    return data


def flash_boot0(dev, payload, backup_root):
    payload = validate_payload(payload)
    device_type = dev.idme_read(b"device_type_id").rstrip(b"\0")
    if device_type not in (b"A31DTMEEVDDOIV", b"A265XOI9586NML"):
        raise RuntimeError(f"Wrong device_type_id: {device_type!r}")

    def read(start, blocks):
        data = b"".join(dev.emmc_read(start + i) for i in range(blocks))
        if len(data) != blocks * 512:
            raise RuntimeError("Incomplete eMMC read; stopping")
        return data

    dev.emmc_switch(0)
    lk = read(1024, (LK_SIZE + 511) // 512)[:LK_SIZE]
    if hashlib.sha256(lk).hexdigest() != LK_SHA:
        raise RuntimeError("Installed LK mismatch; no writes performed")
    blocks = len(payload) // 512
    try:
        dev.emmc_switch(1)  # boot0 only. Never boot1/RPMB or user-area writes.
        originals = {start: read(start, blocks) for start in SLOTS}
        backup_root.mkdir(parents=True, exist_ok=True)
        saved = Path(tempfile.mkdtemp(prefix="boot0-before-brom-", dir=backup_root))
        for start, data in originals.items():
            (saved / f"original-{start}.bin").write_bytes(data)
        (saved / "README.txt").write_text(
            f"boot0 (eMMC area 1), 512-byte sectors, {blocks} sectors per saved region.\n"
            "Filenames give each region's starting LBA; these are NOT full boot0 images.\n")
        log(f"Original boot0 payload regions saved to {saved}")
        for start in SLOTS:
            log(f"Updating boot0 LBA {start}, {blocks} sectors")
            for i in range(blocks):
                dev.emmc_write(start + i, payload[i * 512:(i + 1) * 512])
            actual = read(start, blocks)
            (saved / f"verified-{start}.bin").write_bytes(actual)
            if actual != payload:
                raise RuntimeError(f"boot0 readback failed at LBA {start}; stopping. Backup: {saved}")
    finally:
        dev.emmc_switch(0)
    log("Both payload slots verified. Preloader/LK/TZ/RPMB/GPT/boot/recovery untouched.")
    return saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", nargs="?", type=Path,
                        default=ROOT / "lk-payload/build/payload.bin")
    parser.add_argument("--crash", action="store_true",
                        help="attempt the original RAM-only preloader-to-BootROM transition")
    args = parser.parse_args()
    with args.payload.open("rb") as f:
        payload = validate_payload(f.read(0x80001))
    for name in ("stage1/stage1.bin", "stage2/stage2.bin"):
        if not (ROOT / "brom-payload" / name).is_file():
            raise RuntimeError("Missing SRAM payloads; run: make -C brom-payload")
    check_modemmanager()
    os.chdir(ROOT / "modules")
    dev = Device()
    try:
        dev.find_brom(crash=args.crash)
        load_payload(dev)
        flash_boot0(dev, payload, ROOT / "bin")
        time.sleep(5)
        log("No automatic reboot. Disconnect/reconnect to leave the SRAM payload.")
    finally:
        if dev.dev is not None:
            dev.dev.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        raise SystemExit(str(error))

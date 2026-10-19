#!/usr/bin/env python3
"""Flash only the two Sheldon GPT regions using Kamakiri's SRAM payload."""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile
import time

from common import Device
from functions import check_modemmanager, dump_binary, flash_data
from load_payload import load_payload
from logger import log

ROOT = Path(__file__).resolve().parent.parent
# ponytail: pinned to verified S0 GUIDs; revalidate after changing identifiers.
# Hash order: stock, vendor/128, no-vendor/64, vendor/64; target indices must match.
REGIONS = (
    ("primary", 0, 34, (
        "2b8d67246c87fe66f6e432fed251a2869d497ce164bb89e4f2823721258abc41",
        "de2b9bf6c3630558fe1d080aea985f252b077fb267ce2c19efb714bbf612bf17",
        "e80d3348b4d07313945f2113c7d075eeab58b19cbbc54dd9d3d4494ebef0cfa6",
        "4645872c730de8534c10c4824e59bd549f189dcd47d470d253e949d64ea73b0a",
    )),
    ("backup", 15273567, 33, (
        "63be274912c6e02b65d23500585277cf503a02893630c11414082fbf4a7d284e",
        "b5dc6e13c25030a21c156f7db4659b463ced490d69f69ac90d8df857ed4b0702",
        "d5f54f9760174f32b3a18bb345965464581af4095e39a96459ee28e8a55e0c1c",
        "45f56013cb184c59e42a5e754da1816ad8779ce118fafb01c9fb203655fcb933",
    )),
)


def validate_images(images):
    profiles = set()
    for name, _, blocks, hashes in REGIONS:
        data = images[name]
        digest = hashlib.sha256(data).hexdigest()
        if len(data) != blocks * 512 or digest not in hashes[1:]:
            raise RuntimeError(f"Unexpected target {name} GPT; refusing to flash")
        profiles.add(hashes.index(digest))
    if len(profiles) != 1:
        raise RuntimeError("Mixed target GPT profiles; refusing to flash")


def load_images(directory):
    images = {}
    for name, _, blocks, _ in REGIONS:
        with (directory / f"gpt-{name}.bin").open("rb") as f:
            images[name] = f.read(blocks * 512 + 1)
    validate_images(images)
    return images


def flash_gpt(dev, images, backup_root):
    validate_images(images)
    device_type = dev.idme_read(b"device_type_id").rstrip(b"\0")
    if device_type not in (b"A31DTMEEVDDOIV", b"A265XOI9586NML"):
        raise RuntimeError(f"Wrong device_type_id: {device_type!r}")
    dev.emmc_switch(0)  # User area only; never boot0/boot1/RPMB.
    backup_root.mkdir(parents=True, exist_ok=True)
    saved = Path(tempfile.mkdtemp(prefix="gpt-before-brom-", dir=backup_root))
    log(f"Saving current GPT to {saved}")
    for name, start, blocks, _ in REGIONS:
        dump_binary(dev, str(saved / f"original-{name}.bin"), start, blocks * 512)
    for name, _, _, hashes in REGIONS:
        current = (saved / f"original-{name}.bin").read_bytes()
        if hashlib.sha256(current).hexdigest() not in hashes:
            raise RuntimeError(f"Unknown/corrupt current {name} GPT; no writes performed")

    for name, start, blocks, _ in reversed(REGIONS):
        log(f"Flashing {name} GPT: LBA {start}, {blocks} sectors")
        flash_data(dev, images[name], start, max_size=blocks * 512)
        check = saved / f"verified-{name}.bin"
        dump_binary(dev, str(check), start, blocks * 512)
        if check.read_bytes() != images[name]:
            raise RuntimeError(f"{name} GPT readback failed; stopping immediately")
    log("Both GPT copies verified. No partition contents or boot firmware changed.")
    return saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path,
                        default=ROOT / "bin/gpt-openwrt-128", help="directory containing the validated GPT pair")
    parser.add_argument("--crash", action="store_true",
                        help="attempt the original RAM-only preloader-to-BootROM transition")
    args = parser.parse_args()
    images = load_images(args.directory.resolve())
    for name in ("stage1/stage1.bin", "stage2/stage2.bin"):
        path = ROOT / "brom-payload" / name
        if not path.is_file():
            raise RuntimeError(f"Missing {path}; run: make -C brom-payload")
    check_modemmanager()
    os.chdir(ROOT / "modules")  # Existing load_payload() resolves SRAM binaries here.
    dev = Device()
    try:
        dev.find_brom(crash=args.crash)
        load_payload(dev)
        flash_gpt(dev, images, ROOT / "bin")
        time.sleep(5)  # Same eMMC settling interval as bootrom-step.
        log("No reboot or MISC flags changed. Disconnect/reconnect to leave the SRAM payload.")
    finally:
        if dev.dev is not None:
            dev.dev.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        raise SystemExit(str(error))

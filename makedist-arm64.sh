#!/bin/bash
# No argument: boot0 payload only. Optional image: retain the payload + boot update.
# Usage: ./makedist-arm64.sh [boot-arm64-kamakiri.img]
set -euo pipefail
cd "$(dirname "$0")"
[ "$#" -le 1 ] || { echo "usage: $0 [boot-arm64-kamakiri.img]" >&2; exit 1; }
IMG=${1:-}
OUT="$PWD/dist/kamakiri-arm64-payload.zip"
[ -z "$IMG" ] || OUT="$PWD/dist/kamakiri-arm64-update.zip"

make -C lk-payload test
make -C lk-payload
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
python3 - "$STAGE/update.zip" "$IMG" <<'PY'
import hashlib
from pathlib import Path
import struct
import sys
import zipfile

lk = Path('bin/lk.bin').read_bytes()
pinned = '4da5843f7cbdb537520578e3e0d39e28110d7c2d2f812b4dbc9cbbdd348d6116'
if hashlib.sha256(lk).hexdigest() != pinned:
    raise SystemExit('bin/lk.bin is not the verified Kamakiri LK; refusing to package')
payload = Path('lk-payload/build/payload.bin').read_bytes()
if not 0 < len(payload) <= 0x80000:
    raise SystemExit('Payload exceeds the reserved 512 KiB RAM region')
payload += bytes(-len(payload) % 512)
image = b''
if sys.argv[2]:
    path = Path(sys.argv[2])
    if not path.is_file() or not 2048 <= path.stat().st_size <= 16 * 1024 * 1024:
        raise SystemExit('Missing boot image or image does not fit the 16 MiB boot partition')
    image = path.read_bytes()
    marker = b'bootopt=64S3,32N2,64N2'
    if image[:8] != b'ANDROID!' or image[0x400:0x408] != b'ANDROID!':
        raise SystemExit('Image must already have the Kamakiri microloader prefix')
    if struct.unpack_from('<I', image, 0x400 + 36)[0] != 2048:
        raise SystemExit('Real Android header must use 2048-byte pages')
    if image[0x440:0x440 + len(marker)] != marker or image[0x440 + len(marker)] not in (0, 9, 32):
        raise SystemExit('Real cmdline must start with the canonical ARM64 bootopt token')
values = {
    'LK_SIZE': str(len(lk)), 'LK_SHA256': pinned,
    'PAYLOAD_SIZE': str(len(payload)), 'PAYLOAD_SHA256': hashlib.sha256(payload).hexdigest(),
    'FLASH_BOOT': str(int(bool(image))), 'BOOT_SIZE': str(len(image)),
    'BOOT_SHA256': hashlib.sha256(image).hexdigest(),
}
installer = Path('arm64/META-INF/com/google/android/update-binary').read_text()
for name, value in values.items():
    installer = installer.replace('__' + name + '__', value)
if '__' in installer:
    raise SystemExit('Unfilled installer placeholders')
mode = 'Payload + injected boot image.\n' if image else 'PAYLOAD ONLY: boot image/ROM are not included or changed.\n'
files = {
    'META-INF/com/google/android/update-binary': installer.encode(),
    'META-INF/com/google/android/updater-script': Path('arm64/META-INF/com/google/android/updater-script').read_bytes(),
    'arm64/payload.bin': payload,
    'arm64/README.txt': mode.encode() + Path('arm64/README.txt').read_bytes(),
}
if image:
    files['arm64/boot-arm64-kamakiri.img'] = image
with zipfile.ZipFile(sys.argv[1], 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for name, data in files.items():
        info = zipfile.ZipInfo(name)
        info.create_system = 3
        info.external_attr = (0o100755 if name.endswith('/update-binary') else 0o100644) << 16
        archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
PY
if [ -z "$IMG" ]; then
    python3 package_bootrom.py boot0 "$STAGE/update.zip"
    python3 test_boot0.py "$STAGE/update.zip"
fi
python3 test_arm64.py "$STAGE/update.zip"
mkdir -p dist
mv "$STAGE/update.zip" "$OUT"
printf '%s ready (existing Kamakiri required; no GPT/LK/preloader changes)\n' "$OUT"

#!/usr/bin/env python3
"""Run the real TWRP payload installer against FILES; never access hardware."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile


def check(archive):
    archive = Path(archive).resolve()
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        files = {name: z.read(name) for name in z.namelist()}
        installer = files['META-INF/com/google/android/update-binary'].decode()
        assert (z.getinfo('META-INF/com/google/android/update-binary').external_attr >> 16) & 0o111
    assert '__' not in installer
    assert 'hash()' not in installer, "hash conflicts with mksh's predefined alias"
    payload = files['arm64/payload.bin']
    raw = (Path(__file__).resolve().parent / 'lk-payload/build/payload.bin').read_bytes()
    assert payload == raw + bytes(-len(raw) % 512)
    assert 'gpt' not in ' '.join(files).lower()
    mode = int(re.search(r'^FLASH_BOOT=(\d+)$', installer, re.M).group(1))
    assert ('arm64/boot-arm64-kamakiri.img' in files) == bool(mode)
    lk = (Path(__file__).resolve().parent / 'bin/lk.bin').read_bytes()
    # Regression: sector padding must NOT be included in the pinned LK hash.
    lk_sectors = lk + b'\xa5' * (-len(lk) % 512)
    assert hashlib.sha256(lk).digest() != hashlib.sha256(lk_sectors).digest()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        dev = root / 'dev'
        dev.mkdir()
        boot0, boot, lkdev = (dev / n for n in ('mmcblk0boot0', 'mmcblk0p4', 'mmcblk0p1'))
        sysfs = root / 'sys'
        for name, value in {
            'mmcblk0/queue/logical_block_size': '512', 'mmcblk0boot0/size': '8192',
            'mmcblk0boot0/force_ro': '1', 'mmcblk0p4/size': '32768', 'mmcblk0p4/dev': '259:4',
        }.items():
            p = sysfs / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(value + '\n')
        ro = sysfs / 'mmcblk0boot0/force_ro'
        mounts, writes, script = root / 'mountinfo', root / 'writes', root / 'installer'
        tools = root / 'tools'
        tools.mkdir()
        bodies = {
            'getprop': '#!/bin/sh\ncase "$1" in ro.twrp.version) [ "${NO_TWRP:-0}" = 1 ] || echo 3.7;; ro.product.device) echo "${TEST_DEVICE:-sheldon}";; esac\n',
            'sync': '#!/bin/sh\nexit 0\n',
            'toybox': '#!/bin/sh\n[ "$1" = dd ] || exit 1\nshift\nTWRP_DD=1 exec dd "$@"\n',
            # Match the real recovery: wildcard includes silently extract nothing.
            'unzip': r'''#!/bin/sh
for arg do
    case "$arg" in *\**) exit 0 ;; esac
done
command -p unzip "$@"
''',
            'dd': '''#!/bin/sh
write=0; where=
for arg do
    # The standalone Android dd has conv disabled; Toybox supports notrunc.
    if [ "$arg" = conv=notrunc ] && [ "${TWRP_DD:-0}" != 1 ]; then exit 1; fi
    case "$arg" in "of=$FAKE_BOOT0") write=1;; seek=*) where=${arg#seek=};; esac
done
if [ "$write" = 1 ]; then
    echo "$where" >> "$WRITE_LOG"
    [ "${FAIL_BACKUP:-0}" = 1 ] && [ "$where" = 4096 ] && exit 1
    [ "${FAIL_PRIMARY:-0}" = 1 ] && [ "$where" = 1024 ] && exit 1
fi
command -p dd "$@" || exit $?
if [ "$write" = 1 ] && [ "$where" = 4096 ] && [ "${CORRUPT_BACKUP:-0}" = 1 ]; then
    python3 -c 'import sys; f=open(sys.argv[1],"r+b"); f.seek(2097152); b=f.read(1); f.seek(2097152); f.write(bytes([b[0]^1])); f.close()' "$FAKE_BOOT0"
fi
''',
        }
        for name, body in bodies.items():
            p = tools / name
            p.write_text(body)
            p.chmod(0o755)
        original0 = bytes(range(256)) * 16384
        original_boot = b'EXISTING ROM' + bytes(16 * 1024 * 1024 - 12)

        def reset():
            boot0.write_bytes(original0)
            boot.write_bytes(original_boot)
            lkdev.write_bytes(lk_sectors)
            ro.write_text('1\n')
            mounts.write_text('')
            writes.write_text('')

        def run(source=archive, env=None):
            with zipfile.ZipFile(source) as z:
                text = z.read('META-INF/com/google/android/update-binary').decode()
            for old, new in (
                ('/dev/block', str(dev)), ('/sys/class/block', str(sysfs)),
                ('/proc/self/mountinfo', str(mounts)),
                ('/tmp/kamakiri-arm64.', str(root / 'unpack.')),
                ('/tmp/kamakiri-boot0-backup.', str(root / 'backup.')),
                ('[ -b ', '[ -f '),
            ):
                text = text.replace(old, new)
            assert '/dev/block' not in text and '/sys/class/block' not in text
            script.write_text(text)
            return subprocess.run(
                ['sh', str(script), '3', '1', str(source)], text=True, capture_output=True, timeout=40,
                env={**os.environ, 'PATH': str(tools) + os.pathsep + os.environ['PATH'],
                     'FAKE_BOOT0': str(boot0), 'WRITE_LOG': str(writes), **(env or {})},
            )

        def write_zip(name, contents):
            p = root / name
            with zipfile.ZipFile(p, 'w', compression=zipfile.ZIP_DEFLATED) as z:
                for filename, data in contents.items():
                    z.writestr(filename, data)
            return p

        bad = dict(files)
        bad['arm64/payload.bin'] = bytes([payload[0] ^ 1]) + payload[1:]
        bad_zip = write_zip('bad.zip', bad)
        for failure in ('lk', 'payload', 'device', 'recovery'):
            reset()
            env = {}
            if failure == 'lk':
                lkdev.write_bytes(b'x' + lk_sectors[1:])
            elif failure == 'device':
                env['TEST_DEVICE'] = 'another-device'
            elif failure == 'recovery':
                env['NO_TWRP'] = '1'
            result = run(bad_zip if failure == 'payload' else archive, env)
            assert result.returncode != 0, failure + ': ' + result.stdout
            assert boot0.read_bytes() == original0 and boot.read_bytes() == original_boot
            assert ro.read_text().strip() == '1' and not writes.read_text()

        for failure in ('FAIL_BACKUP', 'CORRUPT_BACKUP', 'FAIL_PRIMARY'):
            reset()
            result = run(env={failure: '1'})
            assert result.returncode != 0, result.stdout + result.stderr
            expected_calls = ['4096', '1024'] if failure == 'FAIL_PRIMARY' else ['4096']
            assert writes.read_text().splitlines() == expected_calls
            assert boot0.read_bytes()[1024 * 512:1024 * 512 + len(payload)] == original0[1024 * 512:1024 * 512 + len(payload)]
            assert boot0.read_bytes()[:512 * 1024] == original0[:512 * 1024]
            assert boot.read_bytes() == original_boot and ro.read_text().strip() == '1'

        reset()
        result = run()
        assert result.returncode == 0, result.stdout + result.stderr
        expected = bytearray(original0)
        for block in (4096, 1024):
            expected[block * 512:block * 512 + len(payload)] = payload
        assert boot0.read_bytes() == expected, 'Writes escaped the two payload regions'
        assert writes.read_text().splitlines() == ['4096', '1024']
        assert ro.read_text().strip() == '1' and lkdev.read_bytes() == lk_sectors
        image = files.get('arm64/boot-arm64-kamakiri.img', b'')
        assert boot.read_bytes() == image + original_boot[len(image):]
        saved = re.search(r'Saving current boot0 to (\S+)', result.stdout).group(1)
        assert Path(saved).read_bytes() == original0
        assert set(dev.iterdir()) == {boot0, boot, lkdev}, 'Installer touched another device'
        ro.write_text('0\n')
        result = run()
        assert result.returncode == 0 and ro.read_text().strip() == '0'
        assert boot0.read_bytes() == expected, 'Repeat update was not idempotent'

        # Exercise the optional image path without ever producing a deployable dummy ZIP.
        if not mode:
            image = bytearray(4096)
            image[:8] = image[1024:1032] = b'ANDROID!'
            image[1088:1110] = b'bootopt=64S3,32N2,64N2'
            variant = dict(files)
            text = re.sub(r'^FLASH_BOOT=.*$', 'FLASH_BOOT=1', installer, flags=re.M)
            text = re.sub(r'^BOOT_SIZE=.*$', 'BOOT_SIZE=' + str(len(image)), text, flags=re.M)
            text = re.sub(r'^BOOT_SHA=.*$', 'BOOT_SHA=' + hashlib.sha256(image).hexdigest(), text, flags=re.M)
            variant['META-INF/com/google/android/update-binary'] = text.encode()
            variant['arm64/boot-arm64-kamakiri.img'] = image
            optional = write_zip('optional-test-only.zip', variant)
            reset()
            mounts.write_text('1 0 259:4 / /unusual-alias rw - ext4 /dev/root rw\n')
            result = run(optional)
            assert result.returncode != 0 and not writes.read_text()
            reset()
            result = run(optional)
            assert result.returncode == 0, result.stdout + result.stderr
            assert boot.read_bytes() == image + original_boot[len(image):]
            assert ro.read_text().strip() == '1'
    print('PASS: payload ZIP, exact LK hash bounds, guards, backup-first/readback failures, force_ro restore, writes confined to requested regions (simulation)')
    print('PASS: optional image backup/mount guard/readback (simulation)')


if __name__ == '__main__':
    check(sys.argv[1])

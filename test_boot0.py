#!/usr/bin/env python3
"""BootROM boot0 updater regression checks using memory only, never USB."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'modules'))
import boot0_flash as updater

RAW = (ROOT / 'lk-payload/build/payload.bin').read_bytes()
PAYLOAD = updater.validate_payload(RAW)
BLOCKS = len(PAYLOAD) // 512
BEFORE = bytes(range(256)) * 16384
USER = bytearray(2 * 1024 * 1024)
lk = (ROOT / 'bin/lk.bin').read_bytes()
USER[1024 * 512:1024 * 512 + len(lk)] = lk
USER[1024 * 512 + len(lk):1024 * 512 + (len(lk) + 511) // 512 * 512] = b'\xa5' * (-len(lk) % 512)


class FakeDevice:
    def __init__(self, fault=None):
        self.fault, self.area = fault, 0
        self.boot0, self.user = bytearray(BEFORE), bytearray(USER)
        self.writes = []

    def idme_read(self, name):
        assert name == b'device_type_id'
        return b'wrong' if self.fault == 'device' else b'A31DTMEEVDDOIV\0'

    def emmc_switch(self, area):
        assert area in (0, 1), 'Accessed boot1/RPMB'
        self.area = area

    def emmc_read(self, block):
        if self.area == 0:
            assert 1024 <= block < 1024 + (len(lk) + 511) // 512
            data = bytes(self.user[block * 512:(block + 1) * 512])
            if self.fault == 'lk' and block == 1024:
                data = bytes([data[0] ^ 1]) + data[1:]
        else:
            assert any(start <= block < start + BLOCKS for start in updater.SLOTS)
            data = bytes(self.boot0[block * 512:(block + 1) * 512])
            if self.fault == 'short':
                return data[:-1]
            if self.fault == 'readback' and self.writes and block == 4096:
                data = bytes([data[0] ^ 1]) + data[1:]
        return data

    def emmc_write(self, block, data):
        assert self.area == 1 and len(data) == 512
        assert any(start <= block < start + BLOCKS for start in updater.SLOTS)
        if (self.fault == 'backup-write' and block == 4096) or (self.fault == 'primary-write' and block == 1024):
            raise RuntimeError('simulated write failure')
        self.boot0[block * 512:(block + 1) * 512] = data
        self.writes.append(block)


def reject(callback):
    try:
        callback()
    except RuntimeError:
        return
    raise AssertionError('Unsafe input/operation accepted')


def check():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for i, data in enumerate((b'', b'x' * 0x80001, bytes([RAW[0] ^ 1]) + RAW[1:])):
            dev = FakeDevice()
            reject(lambda: updater.flash_boot0(dev, data, root / str(i)))
            assert not dev.writes and dev.boot0 == BEFORE and dev.user == USER
        for fault in ('device', 'lk', 'short', 'backup-write', 'readback', 'primary-write'):
            dev = FakeDevice(fault)
            reject(lambda: updater.flash_boot0(dev, RAW, root / fault))
            assert dev.area == 0 and dev.user == USER
            assert dev.boot0[1024 * 512:1024 * 512 + len(PAYLOAD)] == BEFORE[1024 * 512:1024 * 512 + len(PAYLOAD)]
            expected = bytearray(BEFORE)
            if fault in ('readback', 'primary-write'):
                expected[4096 * 512:4096 * 512 + len(PAYLOAD)] = PAYLOAD
                assert dev.writes == list(range(4096, 4096 + BLOCKS))
            else:
                assert not dev.writes
            assert dev.boot0 == expected
            if fault in ('backup-write', 'readback', 'primary-write'):
                saved = next((root / fault).glob('boot0-before-brom-*'))
                for start in updater.SLOTS:
                    assert (saved / f'original-{start}.bin').read_bytes() == BEFORE[start * 512:start * 512 + len(PAYLOAD)]
        dev = FakeDevice()
        expected = bytearray(BEFORE)
        for start in updater.SLOTS:
            expected[start * 512:start * 512 + len(PAYLOAD)] = PAYLOAD
        for i in range(2):
            before = bytes(dev.boot0)
            saved = updater.flash_boot0(dev, RAW, root / 'success')
            assert dev.boot0 == expected and dev.user == USER and dev.area == 0
            assert dev.writes[-2 * BLOCKS:] == list(range(4096, 4096 + BLOCKS)) + list(range(1024, 1024 + BLOCKS))
            for start in updater.SLOTS:
                assert (saved / f'original-{start}.bin').read_bytes() == before[start * 512:start * 512 + len(PAYLOAD)]
                assert (saved / f'verified-{start}.bin').read_bytes() == PAYLOAD
    # The CLI must reject preloader before loading any SRAM payload or flashing.
    class Preloader:
        dev = None
        preloader = True
        find_brom = updater.Device.find_brom
        def find_device(self):
            pass
    def forbidden_load(dev):
        raise AssertionError('Preloader reached the SRAM loader')
    original = updater.Device, updater.check_modemmanager, updater.load_payload, sys.argv, Path.cwd()
    try:
        updater.Device = Preloader
        updater.check_modemmanager = lambda: None
        updater.load_payload = forbidden_load
        sys.argv = ['boot0_flash.py']
        try:
            updater.main()
        except RuntimeError as error:
            assert 'BootROM mode, not preloader' in str(error)
        else:
            raise AssertionError('Preloader mode was accepted')
    finally:
        updater.Device, updater.check_modemmanager, updater.load_payload, sys.argv, cwd = original
        os.chdir(cwd)
    print('PASS: BootROM boot0-only bounds, exact LK hash, backups, backup-first/readback failures, guards including preloader, area restore, idempotence (simulation)')


def check_zip(path):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        assert z.read('lk-payload/build/payload.bin') == RAW
        assert z.read('arm64/payload.bin') == PAYLOAD
        for name in ('boot0-bootrom-flash.sh', 'modules/boot0_flash.py', 'brom-payload/stage1/stage1.bin', 'brom-payload/stage2/stage2.bin'):
            assert z.read(name) == (ROOT / name).read_bytes()
        for name in ('boot0-bootrom-flash.sh', 'META-INF/com/google/android/update-binary'):
            assert (z.getinfo(name).external_attr >> 16) & 0o111
        for line in z.read('SHA256SUMS').decode().splitlines():
            digest, name = line.split('  ', 1)
            assert hashlib.sha256(z.read(name)).hexdigest() == digest
        assert not any(Path(n).name in ('preloader.img', 'lk.bin', 'tz.img', 'twrp.img', 'main.py', 'bootrom-step.sh') for n in z.namelist())
    print('PASS: boot0 dual BootROM/TWRP ZIP, identical payloads, native files, permissions and checksums')


if __name__ == '__main__':
    check()
    if len(sys.argv) > 1:
        check_zip(sys.argv[1])

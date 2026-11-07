#!/usr/bin/env python3
"""Host-only live installer checks: python3 gpt/test_live.py [runtime.zip].

Without an archive, exercise the current installer template with synthetic GPTs.
With an archive, validate its ARM payload before replacing only that executable
and its digest in a temporary ZIP. Never opens a device or invokes adb.
"""
import hashlib
import os
from pathlib import Path
import shlex
import struct
import subprocess
import sys
import tempfile
import zipfile

from test_generate import fixture, verify
from test_gpt import check_zip

INSTALLER = 'META-INF/com/google/android/update-binary'
UPDATER = 'META-INF/com/google/android/updater-script'
GENERATOR = 'gpt/gpt-generate'


def check_runtime(entries):
    assert set(entries) == {INSTALLER, UPDATER, GENERATOR, 'gpt/README.txt'}, 'Unexpected runtime ZIP entries'
    binary = entries[GENERATOR]
    assert binary[:7] == b'\x7fELF\x01\x01\x01', 'Expected little-endian ARM32 ELF'
    assert struct.unpack_from('<H', binary, 18)[0] == 40, 'Expected ARM machine'
    offset = struct.unpack_from('<I', binary, 28)[0]
    size, count = struct.unpack_from('<HH', binary, 42)
    assert size == 32 and count and offset + size * count <= len(binary)
    assert all(struct.unpack_from('<I', binary, offset + i * size)[0] not in (2, 3)
               for i in range(count)), 'Generator must be static (no DYNAMIC/INTERP)'
    lines = entries[INSTALLER].decode().splitlines()
    for line in ('GENERATE=1', 'CHECK_HASH=0', 'SECTORS=0',
                 'GENERATOR_SHA=' + hashlib.sha256(binary).hexdigest()):
        assert line in lines, f'Missing runtime setting: {line}'
    for key in ('PRIMARY_SHA', 'BACKUP_SHA', 'ORIGINAL_PRIMARY_SHA', 'ORIGINAL_BACKUP_SHA'):
        assert any(line.startswith(key + '=') for line in lines), key


def main():
    source = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='gpt-live-test-') as tmp:
        root = Path(tmp)
        executable = root / 'gpt-generate'
        subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
            '-std=c99', '-Wall', '-Wextra', '-Werror', '-pedantic', '-O2',
            str(source / 'gpt-generate.c'), '-o', str(executable)], check=True)
        native = executable.read_bytes()
        digest = hashlib.sha256(native).hexdigest()
        if len(sys.argv) > 1:
            with zipfile.ZipFile(sys.argv[1]) as archive:
                infos = archive.infolist()
                assert len(infos) == 4, 'Duplicate/unexpected ZIP entries'
                assert (archive.getinfo(INSTALLER).external_attr >> 16) & 0o111
                entries = {info.filename: archive.read(info) for info in infos}
            check_runtime(entries)
            script = entries[INSTALLER].decode()
            previous = 'GENERATOR_SHA=' + hashlib.sha256(entries[GENERATOR]).hexdigest()
            script = script.replace(previous, 'GENERATOR_SHA=' + digest)
            print('PASS: runtime ZIP contents, settings, static ARM32 ELF and digest')
        else:
            script = (source / INSTALLER).read_text()
            for key, value in {
                'GENERATE': '1', 'CHECK_HASH': '0', 'SECTORS': '0',
                'GENERATOR_SHA256': digest, 'PRIMARY_SHA256': '-',
                'BACKUP_SHA256': '-', 'ORIGINAL_PRIMARY_SHA256': '-',
                'ORIGINAL_BACKUP_SHA256': '-',
            }.items():
                script = script.replace('__' + key + '__', value)
            assert '__' not in script, 'Unfilled installer template'
            entries = {UPDATER: (source / UPDATER).read_bytes()}
        entries[INSTALLER] = script.encode()
        entries[GENERATOR] = native
        host_zip = root / 'host.zip'
        with zipfile.ZipFile(host_zip, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries.items():
                info = zipfile.ZipInfo(name)
                info.external_attr = (0o100755 if name in (INSTALLER, GENERATOR) else 0o100644) << 16
                archive.writestr(info, data)
        for sectors in (15269888, 15273600):
            directory = root / str(sectors)
            directory.mkdir()
            original = fixture(sectors)
            expected = fixture(sectors, installed=True)
            verify(*expected, sectors, original[0])
            for prefix, pair in (('original', original), ('gpt', expected)):
                for copy, data in zip(('primary', 'backup'), pair):
                    (directory / f'{prefix}-{copy}.bin').write_bytes(data)
            (directory / 'layout.sfdisk').write_text('name="vendor"\n')
            check_zip(directory, host_zip, sectors)


if __name__ == '__main__':
    main()

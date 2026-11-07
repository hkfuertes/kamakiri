#!/usr/bin/env python3
"""Self-contained checks: python3 gpt/test_generate.py (requires host cc)."""
import os
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile
import uuid
import zlib

TYPE = uuid.UUID('0fc63daf-8483-4772-8e79-3d69d8477de4').bytes_le
NAMES = ['lk', 'tee1', 'tee2', 'boot', 'recovery', 'logo', 'kb', 'dkb',
         'MISC', 'vendor', 'system', 'cache', 'userdata']
STARTS = [1024, 3072, 13312, 23552, 56320, 89088, 96256, 98304,
          100352, 102400, 409600, 3481600, 4530176]
TABLE_SIZE = 16384


def guid(n):
    return uuid.UUID(int=n).bytes_le


def seal(h, table):
    struct.pack_into('<I', h, 88, zlib.crc32(table))
    struct.pack_into('<I', h, 16, 0)
    struct.pack_into('<I', h, 16, zlib.crc32(h[:92]))
    return h


def fixture(sectors, installed=False):
    table = bytearray(TABLE_SIZE)
    count = 11 if installed else 13
    for i in range(count):
        end = sectors - 34 if i == count - 1 else STARTS[i + 1] - 1
        entry = struct.pack('<16s16sQQQ72s', TYPE, guid(i + 2), STARTS[i],
                            end, i << 48, NAMES[i].encode('utf-16le'))
        table[i * 128:(i + 1) * 128] = entry

    def header(back):
        h = bytearray(512)
        struct.pack_into('<8sIIIIQQQQ16sQIII', h, 0, b'EFI PART', 0x10000,
                         92, 0, 0, sectors - 1 if back else 1,
                         1 if back else sectors - 1, 34, sectors - 34,
                         guid(1), sectors - 33 if back else 2, 128, 128, 0)
        return seal(h, table)

    mbr = bytearray((i * 17) % 256 for i in range(512))
    mbr[510:] = b'\x55\xaa'
    return mbr + header(False) + table, table + header(True)


def retable(primary, backup, table):
    p, b = bytearray(primary), bytearray(backup)
    p[1024:] = table
    b[:TABLE_SIZE] = table
    p[512:1024] = seal(p[512:1024], table)
    b[TABLE_SIZE:] = seal(b[TABLE_SIZE:], table)
    return p, b


def verify(p, b, sectors, source):
    assert len(p) == 34 * 512 and len(b) == 33 * 512
    assert p[:512] == source[:512]
    table = p[1024:]
    assert table == b[:TABLE_SIZE]
    assert table[:1280] == source[1024:2304]
    expected_system = bytearray(source[2304:2432])
    struct.pack_into('<Q', expected_system, 40, sectors - 34)
    assert table[1280:1408] == expected_system
    assert not any(table[1408:])
    for h, back in [(p[512:1024], False), (b[TABLE_SIZE:], True)]:
        assert h[:8] == b'EFI PART'
        assert struct.unpack_from('<II', h, 8) == (0x10000, 92)
        assert struct.unpack_from('<I', h, 20)[0] == 0
        assert struct.unpack_from('<QQQQ', h, 24) == (
            sectors - 1 if back else 1, 1 if back else sectors - 1,
            34, sectors - 34)
        assert h[56:72] == source[568:584] == guid(1)
        assert struct.unpack_from('<QII', h, 72) == (
            sectors - 33 if back else 2, 128, 128)
        stored = struct.unpack_from('<I', h, 16)[0]
        check = bytearray(h[:92])
        struct.pack_into('<I', check, 16, 0)
        assert stored == zlib.crc32(check)
        assert struct.unpack_from('<I', h, 88)[0] == zlib.crc32(table)
    # No entry-number gaps and no LBA gaps after the fixed initial alignment.
    last = 1023
    for i in range(11):
        e = table[i * 128:(i + 1) * 128]
        start, end = struct.unpack_from('<QQ', e, 32)
        assert e[:16] == TYPE and start == last + 1 and end >= start
        assert e[56:].decode('utf-16le').rstrip('\0') == NAMES[i]
        last = end
    assert last == sectors - 34


def main():
    with tempfile.TemporaryDirectory(prefix='gpt-generate-test-') as d:
        root = Path(d)
        exe = root / 'gpt-generate'
        subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
            '-std=c99', '-Wall', '-Wextra', '-Werror', '-pedantic', '-O2',
            str(Path(__file__).with_name('gpt-generate.c')), '-o', str(exe)],
            check=True)
        ip, ib, op, ob = [root / n for n in ('in-p', 'in-b', 'out-p', 'out-b')]

        def run(p, b, sectors=15273600, success=True, outputs=None):
            ip.write_bytes(p)
            ib.write_bytes(b)
            for path in (op, ob):
                path.unlink(missing_ok=True)
            outp, outb = outputs or (op, ob)
            result = subprocess.run([str(exe), str(sectors), str(ip), str(ib),
                                     str(outp), str(outb)], capture_output=True)
            assert (result.returncode == 0) == success, result.stderr
            if not success:
                assert not op.exists() and not ob.exists(), result.stderr
            assert ip.read_bytes() == p and ib.read_bytes() == b
            if success:
                return op.read_bytes(), ob.read_bytes()

        for sectors in (15269888, 15273600):
            p, b = fixture(sectors)
            generated = run(p, b, sectors)
            verify(*generated, sectors, p)
            assert generated == fixture(sectors, installed=True)
            assert run(*generated, sectors) == generated
            for side, offset in [(0, 512 + 16), (1, TABLE_SIZE + 16),
                                 (0, 1024 + 100), (1, 100)]:
                damaged = [bytearray(p), bytearray(b)]
                damaged[side][offset] ^= 1
                run(*damaged, sectors, success=False)

        p, b = fixture(15273600)
        for sectors in (0, 15273601, '015273600', '15273600x'):
            run(p, b, sectors, success=False)
        for badp, badb in [(p[:-1], b), (p + b'x', b), (p, b[:-1]),
                            (p, b + b'x')]:
            run(badp, badb, success=False)
        bad = bytearray(p)
        bad[510] = 0
        run(bad, b, success=False)
        # Invalid but correctly checksummed tables: validation, not just CRCs.
        def mutate_entry(index, offset, data):
            t = bytearray(p[1024:])
            start = index * 128 + offset
            t[start:start + len(data)] = data
            run(*retable(p, b, t), success=False)

        mutate_entry(10, 32, struct.pack('<Q', 409599))  # overlap
        mutate_entry(12, 40, struct.pack('<Q', 15273600))  # bounds
        mutate_entry(0, 32, struct.pack('<Q', 1025))  # unsupported range
        mutate_entry(11, 56, 'strange'.encode('utf-16le'))
        mutate_entry(11, 56, p[2304 + 56:2432])  # duplicate system
        mutate_entry(10, 0, bytes(128))  # missing system / entry gap
        mutate_entry(0, 0, bytes(16))  # missing type
        mutate_entry(1, 16, p[1024 + 16:1024 + 32])  # duplicate GUID
        mutate_entry(10, 16, bytes(16))
        mutate_entry(13, 0, p[1024:1152])  # unexpected extra entry
        mutate_entry(0, 127, b'\x01')  # name trailing garbage
        for offset, data in [(0, b'BAD PART'), (8, struct.pack('<I', 0x20000)),
                             (12, struct.pack('<I', 96)), (20, b'\x01'),
                             (24, struct.pack('<Q', 777)), (32, struct.pack('<Q', 777)),
                             (40, struct.pack('<Q', 35)), (48, struct.pack('<Q', 99)),
                             (56, bytes(16)), (72, struct.pack('<Q', 3)),
                             (80, struct.pack('<I', 127)), (84, struct.pack('<I', 64))]:
            for back in (False, True):
                pair = [bytearray(p), bytearray(b)]
                base = TABLE_SIZE if back else 512
                pair[back][base + offset:base + offset + len(data)] = data
                pair[back][base:base + 512] = seal(
                    pair[back][base:base + 512], p[1024:])
                run(*pair, success=False)
        badb = bytearray(b)
        badb[TABLE_SIZE + 56:TABLE_SIZE + 72] = guid(999)
        badb[TABLE_SIZE:] = seal(badb[TABLE_SIZE:], p[1024:])
        run(p, badb, success=False)  # different disk GUIDs
        t = bytearray(p[1024:])
        t[48] ^= 1
        _, badb = retable(p, b, t)
        run(p, badb, success=False)  # individually valid but different tables
        # Existing files, inputs, symlinks, and identical output paths are safe.
        sentinel = root / 'existing'
        sentinel.write_bytes(b'keep me')
        for outputs in [(sentinel, ob), (op, sentinel), (ip, ob), (op, ib),
                        (op, op)]:
            run(p, b, success=False, outputs=outputs)
            assert sentinel.read_bytes() == b'keep me'
        link = root / 'link'
        link.symlink_to(sentinel)
        run(p, b, success=False, outputs=(link, ob))
        assert sentinel.read_bytes() == b'keep me'
    print('gpt-generate: all checks passed (both capacities, no devices)')


if __name__ == '__main__':
    main()

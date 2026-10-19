#!/usr/bin/env python3
"""Check make-gpt.sh output without accessing any device."""
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import uuid
import zipfile
import zlib


def check_pair(directory, prefix):
    primary = (directory / f"{prefix}-primary.bin").read_bytes()
    backup = (directory / f"{prefix}-backup.bin").read_bytes()
    assert len(primary) == 34 * 512 and len(backup) == 33 * 512
    assert primary[510:512] == b"\x55\xaa"
    table = primary[1024:]
    assert table == backup[:-512], "Primary/backup partition arrays differ"
    headers = (primary[512:1024], backup[-512:])
    for header, current, alternate, entries in (
        (headers[0], 1, 15273599, 2),
        (headers[1], 15273599, 1, 15273567),
    ):
        assert header[:8] == b"EFI PART"
        size, crc = struct.unpack_from("<II", header, 12)
        assert 92 <= size <= 512
        check = bytearray(header[:size])
        check[16:20] = bytes(4)
        assert zlib.crc32(check) == crc, "Bad GPT header CRC"
        assert struct.unpack_from("<QQQQ", header, 24) == (current, alternate, 34, 15273566)
        assert struct.unpack_from("<QIII", header, 72) == (entries, 128, 128, zlib.crc32(table))
    assert headers[0][56:72] == headers[1][56:72], "Disk GUID mismatch"
    cursor = 34
    partitions = []
    for i in range(128):
        entry = table[i * 128:(i + 1) * 128]
        if entry[:16] == bytes(16):
            continue
        start, end = struct.unpack_from("<QQ", entry, 32)
        assert 34 <= start <= end <= 15273566
        partitions.append((start, end, i + 1, entry[56:128].decode("utf-16le").rstrip("\0")))
    for start, end, _, _ in sorted(partitions):
        assert start >= cursor, "Overlapping partitions"
        cursor = end + 1
    return primary, headers, table, partitions


def check_zip(directory, archive):
    without_vendor = 'name="vendor"' not in (directory / "layout.sfdisk").read_text()
    with zipfile.ZipFile(archive) as z:
        for prefix in ("original", "gpt"):
            for copy in ("primary", "backup"):
                name = f"{prefix}-{copy}.bin"
                assert z.read(f"gpt/{name}") == (directory / name).read_bytes()
        info = z.getinfo("META-INF/com/google/android/update-binary")
        assert (info.external_attr >> 16) & 0o111, "Installer is not executable"
        installer = z.read(info.filename).decode()
        assert "__" not in installer, "Unfilled installer hash placeholders"
        assert "hash()" not in installer, "hash conflicts with mksh\'s predefined alias"

    # Run the real installer against a sparse FILE and fake sysfs/getprop/mounts.
    # No block device, real sysfs or hardware is reachable from this copy.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        disk = root / "emmc.img"
        for old, new in (
            ("/dev/block/mmcblk0", str(disk)),
            ("/sys/class/block", str(root / "sys")),
            ("/proc/self/mountinfo", str(root / "mountinfo")),
            ("/tmp/gpt-openwrt.", str(root / "unpack.")),
            ('[ -b "$DEV" ]', '[ -f "$DEV" ]'),
        ):
            installer = installer.replace(old, new)
        assert "/dev/block/" not in installer and "/sys/class/block" not in installer
        script = root / "update-binary"
        script.write_text(installer)
        tools = root / "tools"
        tools.mkdir()
        for name, body in {
            "getprop": '#!/bin/sh\ncase "$1" in ro.twrp.version) echo 3.7;; ro.product.device) echo sheldon;; esac\n',
            "sync": "#!/bin/sh\nexit 0\n",
            # TWRP unzip accepts literal entry names, not include glob patterns.
            "unzip": r'''#!/bin/sh
for arg do
    case "$arg" in *\**) exit 0 ;; esac
done
command -p unzip "$@"
''',
            "toybox": '#!/bin/sh\n[ "$1" = dd ] || exit 1\nshift\nDD_LARGEFILE=1 exec dd "$@"\n',
            "umount": '#!/bin/sh\n[ "${UMOUNT_FAILS:-0}" = 1 ] && exit 1\nawk -v m="$1" \x27$5 != m && index($5, m "/") != 1\x27 "$FAKE_MOUNTINFO" > "$FAKE_MOUNTINFO.new" && mv "$FAKE_MOUNTINFO.new" "$FAKE_MOUNTINFO"\n',
            "dd": '''#!/bin/sh
for arg do
    case "$arg" in
        skip=15273567|seek=15273567) [ "${DD_LARGEFILE:-0}" = 1 ] || exit 1 ;;
    esac
    if [ "${FAIL_GPT_WRITE:-0}" = 1 ] && [ "$arg" = "of=$FAKE_DISK" ]; then exit 1; fi
done
command -p dd "$@"
''',
        }.items():
            path = tools / name
            path.write_text(body)
            path.chmod(0o755)
        for name, value in {
            "mmcblk0/size": "15273600", "mmcblk0/queue/logical_block_size": "512",
            "mmcblk0p10/dev": "259:2", "mmcblk0p11/dev": "259:3",
            "mmcblk0p12/dev": "259:4", "mmcblk0p13/dev": "259:5",
        }.items():
            path = root / "sys" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value + "\n")
        (root / "mountinfo").write_text("")
        old_primary = (directory / "original-primary.bin").read_bytes()
        old_backup = (directory / "original-backup.bin").read_bytes()
        with disk.open("wb") as f:
            f.truncate(15273600 * 512)
            f.write(old_primary)
            f.seek(15273567 * 512)
            f.write(old_backup)
            f.seek(1024 * 512)
            f.write(b"LK MUST NOT CHANGE")

        def snapshot():
            with disk.open("rb") as f:
                primary = f.read(17408)
                f.seek(15273567 * 512)
                backup = f.read(16896)
                f.seek(1024 * 512)
                return primary, backup, f.read(18)

        def run(extra_env=None):
            return subprocess.run(
                ["sh", str(script), "3", "1", str(Path(archive).resolve())],
                env={**os.environ, "PATH": str(tools) + os.pathsep + os.environ["PATH"],
                     "FAKE_DISK": str(disk), "FAKE_MOUNTINFO": str(root / "mountinfo"), **(extra_env or {})},
                capture_output=True, text=True, timeout=30,
            )

        before = snapshot()
        mounts = ["259:3 / /unusual-alias", "259:4 / /unusual-alias",
                  "259:5 / /unusual-alias", "253:0 / /data"]
        if without_vendor:
            mounts += ["259:2 / /unusual-alias", "253:0 / /vendor"]
        for mount in mounts:
            (root / "mountinfo").write_text(f"1 0 {mount} rw - ext4 /dev/root rw\n")
            result = run({"UMOUNT_FAILS": "1"})
            assert result.returncode != 0 and "Cannot unmount" in result.stdout, result.stdout + result.stderr
            assert snapshot() == before, "Installer wrote while a mount was not released"
        (root / "mountinfo").write_text("")
        for part in ((10, 11) if without_vendor else (11,)):
            node = root / "sys" / f"mmcblk0p{part}/dev"
            value = node.read_text()
            node.unlink()
            result = run()
            assert result.returncode != 0 and "Cannot identify" in result.stdout
            assert snapshot() == before
            node.write_text(value)
        # The vendorless kernel exposes neither p12 nor p13.
        if without_vendor:
            for part in (12, 13):
                (root / "sys" / f"mmcblk0p{part}/dev").unlink()
        (root / "mountinfo").write_text("")
        with disk.open("r+b") as f:
            f.seek(512)
            f.write(b"BAD GPT!")
        corrupt = snapshot()
        result = run()
        assert result.returncode != 0 and "Unknown/corrupt primary" in result.stdout, result.stdout + result.stderr
        assert snapshot() == corrupt, "Installer wrote over an unknown GPT"
        with disk.open("r+b") as f:
            f.write(old_primary)
        result = run({"FAIL_GPT_WRITE": "1"})
        assert result.returncode != 0 and "Backup GPT write failed" in result.stdout, result.stdout + result.stderr
        assert snapshot() == before, "Primary GPT changed after backup write failure"
        # A mounted affected partition is unmounted automatically, then the flash proceeds.
        (root / "mountinfo").write_text("1 0 259:4 / /cache rw - ext4 /dev/root rw\n")
        result = run()
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Unmounting /cache" in result.stdout, result.stdout
        assert (root / "mountinfo").read_text() == "", "cache was not unmounted"
        after = snapshot()
        assert after[:2] == ((directory / "gpt-primary.bin").read_bytes(), (directory / "gpt-backup.bin").read_bytes())
        assert after[2] == before[2], "Installer wrote partition contents"
        result = run()
        assert result.returncode == 0 and "already updated" in result.stdout
        assert snapshot() == after
    print("PASS: ZIP installer guards, backup-write failure, both-copy update, unchanged LK, idempotence (host simulation)")


def check_definition(directory, primary, system_size):
    # Exercise the actual generator's GUID expansion, not a second template.
    source = Path(__file__).with_name("make-gpt.sh").read_text()
    helpers = source[source.index("guid() {"):source.index("\n# A sparse")]
    rendered = subprocess.run(
        ["sh", "-c", 'OUT=$1\n' + helpers + '\ndefinition "$2"\n',
         "generator-check", str(directory.resolve()), str(system_size // 2048)],
        check=True, capture_output=True, text=True,
    ).stdout
    disk_guid = str(uuid.UUID(bytes_le=primary[568:584]))
    assert "label-id: " + disk_guid in rendered.lower()
    rows = [line for line in rendered.splitlines() if line.startswith("start=")]
    assert len(rows) == 12
    assert 'name="vendor"' in (directory / "layout.sfdisk").read_text()
    for i, row in enumerate(rows):
        fields = dict(field.strip().split("=", 1) for field in row.split(","))
        entry = primary[1024 + i * 128:1024 + (i + 1) * 128]
        start, end = struct.unpack_from("<QQ", entry, 32)
        assert int(fields["start"]) == start and int(fields["size"]) == end - start + 1
        assert fields["uuid"].lower() == str(uuid.UUID(bytes_le=entry[16:32]))
        assert fields["type"].lower() == str(uuid.UUID(bytes_le=entry[:16]))
        assert fields["name"].strip('"') == entry[56:128].decode("utf-16le").rstrip("\0")
    print("PASS: complete generator definition retains source GUIDs and exact layout")


def main():
    directory = Path(sys.argv[1] if len(sys.argv) > 1 else "bin/gpt-openwrt-128")
    original, old_headers, old_table, old_parts = check_pair(directory, "original")
    primary, headers, table, parts = check_pair(directory, "gpt")
    assert hashlib.sha256(old_table).hexdigest() in {
        "25aea305a221daf2204d7ca7f0d1af571d4944b272c450cbe36a0e9d99a5d26a",
        "fd41582e245a85b5af06bf2880c144086ad7b0180daf743492ab1a1f08cc0acd",
        "d48e33830e03104aa1e7e5ffa56d04dce459df19b43881b60040a4125fa8f305",
        "e0a0559a4e53c781a14c6bebced30da759184e2ffb4f290bcd110ffa9a0b3c65",
        "7ca3a6adf5b39bf21bb0fe2e359454b4eff02221cae0053fd868625a0df8cd8c",
        "689a53584c374ca2f4efebc568396f221cea95cab8857c749bd8ddf2c653b568",
        "6cec64797a3a22e125fdd06c871a2f009a4209b3c7c61104b82a8e68c9c3cf93",
    }
    without_vendor = not any(name == "vendor" for _, _, _, name in parts)
    assert not without_vendor, "vendor must be retained"
    system_number = 11
    system_start = 409600
    system_size = next(end - start + 1 for start, end, _, name in parts if name == "system")
    assert system_size > 0 and system_size % 2048 == 0
    userdata_start = system_start + system_size
    expected = bytearray(len(old_table))
    preserved = system_number - 1
    expected[:preserved * 128] = old_table[:preserved * 128]
    for name, start, end, number in (
        ("system", system_start, userdata_start - 1, system_number),
        ("userdata", userdata_start, 15273566, system_number + 1),
    ):
        old_number = next(n for _, _, n, label in old_parts if label == name)
        entry = bytearray(old_table[(old_number - 1) * 128:old_number * 128])
        struct.pack_into("<QQ", entry, 32, start, end)
        expected[(number - 1) * 128:number * 128] = entry
    assert table == expected, "Unexpected change to partition entries/GUIDs"
    assert primary[:512] == original[:512], "MBR changed"
    for old, new in zip(old_headers, headers):
        old, new = bytearray(old), bytearray(new)
        for offset in (16, 88):
            old[offset:offset + 4] = new[offset:offset + 4] = bytes(4)
        assert old == new, "Unexpected GPT header change"
    assert len(old_parts) in (11, 12, 13) and len(parts) == 12
    assert [number for _, _, number, _ in parts] == list(range(1, len(parts) + 1)), "GPT entry gaps"
    assert (system_start, userdata_start - 1, system_number, "system") in parts
    assert (userdata_start, 15273566, system_number + 1, "userdata") in parts
    print(f"PASS: system={system_size / 2048:g} MiB (p{system_number}), "
          f"userdata={(15273567 - userdata_start) / 2048:.3f} MiB (p{system_number + 1}), no entry gaps")
    print("PASS: both GPT CRCs, no overlaps, unchanged MBR/other partitions/GUIDs")
    check_definition(directory, primary, system_size)
    if len(sys.argv) > 2:
        check_zip(directory, sys.argv[2])


if __name__ == "__main__":
    main()

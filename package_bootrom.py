#!/usr/bin/env python3
"""Add a standalone BootROM updater to an already-built component TWRP ZIP."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
kind, destination = sys.argv[1:3]
if kind != 'boot0':
    raise SystemExit('Expected boot0')
archive = Path(destination)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    files = {i.filename: z.read(i) for i in z.infolist() if not i.is_dir()}
if kind == 'boot0' and 'arm64/boot-arm64-kamakiri.img' in files:
    raise SystemExit('BootROM/TWRP component package must not contain a boot image')
subprocess.run(['make', '-C', str(ROOT / 'brom-payload'), 'stage1/stage1.bin', 'stage2/stage2.bin'], check=True)
subprocess.run([sys.executable, str(ROOT / 'test_brom_connect.py')], check=True)
command = 'boot0-bootrom-flash.sh'
module = 'boot0_flash'
paths = [command, 'modules/' + module + '.py']
paths += ['modules/' + n + '.py' for n in ('common', 'functions', 'load_payload', 'logger')]
paths += ['brom-payload/' + n for n in ('stage1/stage1.bin', 'stage2/stage2.bin')]
paths += ['lk-payload/build/payload.bin']
for name in paths:
    files[name] = (ROOT / name).read_bytes()
files['requirements.txt'] = b'pyserial\npyusb\n'
scope = (
    'BOOT0: solo payload ARM32/ARM64 en LBA 4096 y 1024, backup primero.\n'
    'Verifica LK antes de escribir. BootROM guarda las regiones originales en\n'
    'bin/boot0-before-brom-*/; TWRP guarda boot0 completo en /tmp/kamakiri-boot0-backup.*/.\n'
    'Extraer las copias de TWRP con ADB antes de reiniciar para conservarlas.\n'
    'No incluye kernel/ROM: el kernel ARM64 necesita su cabecera Kamakiri y bootopt.\n'

)
files['README.txt'] = (
    'ACTUALIZACION ' + kind.upper() + ': KAMAKIRI YA INSTALADO\n\n'
    'MISMO ZIP, DOS METODOS ALTERNATIVOS:\n'
    '1. TWRP: flashear este ZIP como update normal. No es necesario descomprimirlo.\n'
    '2. BootROM: descomprimir en una carpeta propia; en Linux instalar Python 3,\n'
    '   python3-serial, python3-usb y libusb-1.0-0; entrar en esa carpeta y ejecutar:\n'
    '     sha256sum -c SHA256SUMS\n'
    '     sudo ./' + command + ' --crash\n'
    '   Iniciar desconectado; conectar el stick al mostrar Waiting for device.\n'
    '   --crash intenta la transicion preloader -> BootROM solo en RAM.\n'
    '   Se vuelve a comprobar BROM antes de cargar SRAM/escribir eMMC.\n'
    '   Sin --crash, se requiere BROM directo; preloader se rechaza.\n'
    '   No hay reinicio automatico despues del flasheo.\n\n'
    + scope + '\n'
    'No es un instalador completo. No ejecutar bootrom-step.sh ni fixgpt.\n'
    'No instala preloader, LK, TZ, RPMB, boot ni recovery. No incluye U-Boot.\n'
    'Las pruebas automaticas del constructor se ejecutan sin acceder al hardware.\n'
).encode()
assert not any(Path(n).name in ('main.py', 'bootrom-step.sh', 'preloader.img', 'lk.bin', 'tz.img', 'twrp.img') for n in files)
files.pop('SHA256SUMS', None)
files['SHA256SUMS'] = ''.join(hashlib.sha256(data).hexdigest() + '  ' + n + '\n' for n, data in sorted(files.items())).encode()
with tempfile.TemporaryDirectory(prefix='kamakiri-component-package-') as temp:
    stage = Path(temp)
    for name, data in files.items():
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=stage, check=True, stdout=subprocess.DEVNULL)
    help_result = subprocess.run(['bash', command, '--help'], cwd=stage, check=True, capture_output=True, text=True,
                                 env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    assert '--crash' in help_result.stdout
    out = stage / 'component.zip'
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = (0o100755 if name.endswith(('.sh', '/update-binary')) else 0o100644) << 16
            z.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        assert all(z.read(n) == data for n, data in files.items())
    archive.write_bytes(out.read_bytes())
print('PASS: ' + kind + ' ZIP supports TWRP and standalone BootROM; checksums/imports/help verified, no device access')

#!/usr/bin/env python3
"""Add a standalone BootROM updater to an already-built GPT TWRP ZIP."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
kind, destination = sys.argv[1:3]
if kind != 'gpt':
    raise SystemExit('Expected gpt')
archive = Path(destination)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    files = {i.filename: z.read(i) for i in z.infolist() if not i.is_dir()}
subprocess.run(['make', '-C', str(ROOT / 'brom-payload'), 'stage1/stage1.bin', 'stage2/stage2.bin'], check=True)
subprocess.run([sys.executable, str(ROOT / 'test_brom_connect.py')], check=True)
command = 'gpt-bootrom-flash.sh'
module = 'gpt_flash'
paths = [command, 'modules/' + module + '.py']
paths += ['modules/' + n + '.py' for n in ('common', 'functions', 'load_payload', 'logger')]
paths += ['brom-payload/' + n for n in ('stage1/stage1.bin', 'stage2/stage2.bin')]
directory = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / 'bin/gpt-openwrt-128'
for name in ('gpt-primary.bin', 'gpt-backup.bin', 'original-primary.bin', 'original-backup.bin',
             'layout.sfdisk', 'original.sfdisk'):
    files['bin/gpt-openwrt-128/' + name] = (directory / name).read_bytes()
layout = (directory / 'layout.sfdisk').read_text()
without_vendor = 'name="vendor"' not in layout
system_row = next(row for row in layout.splitlines() if 'name="system"' in row)
system_mib = int(system_row.split('size=')[1].split(',')[0]) // 2048
gpt_layout = (
    'GPT: p1..p9 intactas, system=p10 de 64 MiB y userdata=p11 con el resto.\n'
    'Se eliminan vendor y cache. SYSTEM SE MUEVE: reflashear OpenWrt despues.\n'
    if without_vendor else
    f'GPT: p1..p10 intactas, system=p11 de {system_mib} MiB y userdata=p12 con el resto.\n'
    'Se elimina cache y se conserva vendor.\n'
)
for name in paths:
    files[name] = (ROOT / name).read_bytes()
files['requirements.txt'] = b'pyserial\npyusb\n'
scope = (
    gpt_layout + 'Se conservan labels y GUIDs, sin huecos entre entradas.\n'
    'Escribe y verifica la GPT secundaria antes de la primaria.\n'
    'TWRP: desmontar System/Cache/Data; instalar desde USB o ADB sideload.\n'
    'REINICIAR RECOVERY antes de recrear userdata: la tabla del kernel puede ser vieja.\n'
    'BootROM: desconectar/reconectar al terminar para cargar la nueva GPT.\n'
    'No mueve datos ni formatea: el usuario recrea userdata por separado.\n'
)
files['README.txt'] = (
    'ACTUALIZACION GPT: KAMAKIRI YA INSTALADO\n\n'
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

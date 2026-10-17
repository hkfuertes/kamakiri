# Sheldon: kernel ARM64 con Kamakiri (experimental)

Esta rama selecciona la ruta ARM64 que ya existe en LK. Los payloads de
Kamakiri siguen siendo ARM32. Se ha observado OpenWrt AArch64 arrancando
con `maxcpus=1`; esto no valida todavía SMP ni todos los periféricos.

## Activación por imagen

La **cmdline de la cabecera Android real** debe empezar exactamente por:

```text
bootopt=64S3,32N2,64N2
```

Puede continuar con un espacio y los argumentos de OpenWrt. El hook selecciona
el modo al leer la cabecera, antes de que LK elija dónde cargar/descomprimir el
kernel. Las imágenes sin ese primer argumento siguen en ARM32: no se fuerza
ARM64 sobre el kernel stock ni sobre TWRP.

No cambies la cmdline de `microloader/inject_microloader.py`: su cabecera falsa
necesita seguir provocando el exploit ARM32. Este cambio cubre el arranque desde
`boot`/`recovery`; no añade selección ARM64 al comando `fastboot boot`.

## LK correspondiente

Las direcciones siguen siendo específicas del LK usado por Kamakiri Sheldon.
Se contrastó el miembro `lk.bin` con esta [copia pública del paquete](https://raw.githubusercontent.com/daboynb/Root_firestick/HEAD/kamakiri-sheldon-1.0.zip);
no se ha verificado una firma del distribuidor:

```text
Paquete inspeccionado: kamakiri-sheldon-1.0.zip
lk.bin: 318880 bytes
SHA256: 4da5843f7cbdb537520578e3e0d39e28110d7c2d2f812b4dbc9cbbdd348d6116
g_is_64bit_kernel: RAM 0x41e5c19c
```

El inicializador en `0x41e0eec4` obtiene esa dirección mediante la entrada en
`0x41e4da04` y escribe 0/1 según `kernel_boot_opt`. Coinciden también los puntos
fijos de este árbol: `get_device=0x41e23229`, `cache_clean=0x41e2353c` y
reentrada `0x41e2585d`. No sustituir este LK por el de una OTA reciente.

## ZIP de actualización del payload: BootROM o TWRP

Requiere **Kamakiri ya instalado** y el LK fijado arriba; no es un instalador
desde stock. TWRP solo es necesario para el método desde recovery. No necesita
una imagen de kernel ni archivos TZ/preloader para actualizar el selector:

```sh
bash makedist-arm64.sh
```

Genera `dist/kamakiri-arm64-payload.zip`, utilizable de dos formas alternativas:
flashear el ZIP en TWRP, o descomprimirlo y ejecutar en Linux:

```sh
unzip dist/kamakiri-arm64-payload.zip -d dist/boot0-update
(cd dist/boot0-update && sudo ./boot0-bootrom-flash.sh --crash)
```

`--crash` intenta la transición preloader → BootROM original de Kamakiri, solo
en RAM, y comprueba de nuevo BROM antes de cargar SRAM o escribir eMMC. Sin el
flag se sigue rechazando preloader. Iniciar antes de conectar el stick.
Ambos métodos verifican LK y solo escriben boot0 en LBA 4096 y después 1024,
verificando cada lectura. No cambian preloader,
LK, TZ, RPMB, GPT, boot ni recovery; no ejecutar el instalador completo
`bootrom-step.sh`/`fixgpt` como sustituto.

BootROM guarda las regiones originales modificadas en `bin/boot0-before-brom-*/`
del paquete descomprimido. TWRP guarda boot0 completo en
`/tmp/kamakiri-boot0-backup.*/boot0.bin` y restaura `force_ro` también si falla;
extraer la copia con ADB antes de reiniciar para conservarla. El hash de LK se
calcula sobre sus 318880 bytes, sin incluir el relleno del último sector.

El payload sigue siendo ARM32. Una imagen ARM64 debe cumplir el formato y
`bootopt` descritos en este documento; el ZIP no incluye una ROM ni U-Boot.

Se mantiene el modo anterior, opcional, que también actualiza `boot`:

```sh
bash makedist-arm64.sh boot-arm64-kamakiri.img
```

Genera `dist/kamakiri-arm64-update.zip`; verifica tamaño/hash de la imagen,
rechaza `boot` montado y guarda también la imagen anterior antes de escribir.
Los instaladores se comprueban con `test_arm64.py`, `test_boot0.py` y
`test_brom_connect.py` usando archivos/dispositivos simulados; no sustituye
probar los ZIP en hardware real.

## Imagen necesaria (cuando se compile el kernel)

- Kernel **AArch64 `Image.gz` con un DTB mainline de Sheldon añadido**. No sirve
  el zImage ARM32 de la OTA ni se ha demostrado que su DTB Android sirva a mainline.
- Cabecera Android legacy, página de 2048 bytes, cmdline anterior como primer
  argumento. Mantener los argumentos en los primeros 512 bytes de cmdline.
- `kernel_addr` alineada a 512 KiB **y** compatible con `text_offset` y las
  condiciones de colocación del header ARM64 `Image`.
- LK pasa una capacidad de salida de 28 MiB al descompresor. Evitar solapar
  el kernel/DTB/initramfs con LK (`0x41e00000..0x41f00000`), el payload aún
  activo (`0x41000000..0x41080000`) o el staging (`0x45000000`). También hay
  que respetar las reservas del firmware y del DTB.
- El DTB y el estado de CPU deben cumplir el
  [protocolo de entrada ARM64](https://docs.kernel.org/arch/arm64/booting.html).

Una vez exista un `boot-arm64.img` Android estándar, sin prefijo Kamakiri, el
inyector existente conserva el layout sin desplazar el kernel:

```sh
python3 microloader/inject_microloader.py boot-arm64.img \
    microloader/build/payload.bin boot-arm64-kamakiri.img
```

Esto solo genera un archivo; no flashea. Requiere el microloader previamente
compilado. El layout final es: prefijo exploit en `0x000..0x3ff`, cabecera real
en `0x400..0x7ff` y kernel a partir de `0x800`. El contenido completo debe caber
en la partición de destino (16 MiB para `boot` en el GPT de referencia).

## Comprobación sin compilar firmware

```sh
make -C lk-payload test
```

Solo compila y ejecuta en el host el selector de cabecera. No ejecuta firmware
ni accede al dispositivo. El arranque OpenWrt AArch64 se ha comprobado por
SSH en el dispositivo; esta prueba de host no valida PSCI/SMP ni periféricos.

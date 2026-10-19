# Sheldon: un payload para kernels ARM32 y ARM64

El payload de Kamakiri sigue siendo ARM32; el mismo binario permite a LK
arrancar un kernel ARM32 o ARM64 según la cabecera de cada imagen.
`makedist.sh` ya incluye `lk-payload/build/payload.bin`: no hace falta otro
payload, script de distribución ni ZIP específico para ARM64.

## Selección por imagen

La cmdline de la cabecera Android real debe empezar por este argumento
completo para seleccionar ARM64:

```text
bootopt=64S3,32N2,64N2
```

Después puede terminar o continuar con un espacio o tabulador y otros
argumentos. Las imágenes sin ese primer argumento conservan ARM32, incluidos
el kernel stock y TWRP. La selección se hace por imagen de `boot` o `recovery`;
no se añade soporte ARM64 a `fastboot boot`.

No es autodetección del contenido del kernel: LK necesita elegir la ruta de
carga antes de descomprimirlo. Un kernel ARM64 debe declararlo en su cabecera.
No hay que cambiar la cabecera falsa del inyector existente.

## Compatibilidad

Solo corresponde al LK de Kamakiri Sheldon de 318880 bytes, con SHA256:

```text
4da5843f7cbdb537520578e3e0d39e28110d7c2d2f812b4dbc9cbbdd348d6116
```

Las direcciones del payload son específicas de ese LK; no sustituirlo por el
de una OTA reciente. El selector no verifica ese hash en ejecución.

La imagen ARM64 necesita una cabecera Android legacy con página de 2048 bytes,
`Image.gz` y un DTB compatible. No convierte el zImage ARM32 de la OTA en ARM64.
Hay que respetar la alineación y colocación del kernel, los límites de la
partición, las reservas del firmware/DTB y el
[protocolo de entrada ARM64](https://docs.kernel.org/arch/arm64/booting.html).
LK limita la salida del descompresor a 28 MiB; no solapar kernel/DTB/initramfs
con LK (`0x41e00000..0x41f00000`), el payload activo
(`0x41000000..0x41080000`) ni el staging (`0x45000000`).

Se observó OpenWrt AArch64 arrancando con `maxcpus=1`; no valida SMP ni todos
los periféricos.

## Distribución y comprobación

Los instaladores originales quedan sin cambios. Son instalaciones completas;
**no usarlos como actualización de solo payload**. Esta rama no incluye los
actualizadores independientes BootROM/TWRP ni flashea automáticamente un kernel.

```sh
make -C lk-payload test
```

La prueba ejecuta solo el selector en el host: comprueba ARM64 explícito,
ARM32 por defecto, tokens y límites de lectura. No accede al dispositivo ni
valida el arranque real.

# Sheldon: kernel ARM64 con Kamakiri (experimental)

Esta rama selecciona la ruta ARM64 que ya existe en LK. Los payloads de
Kamakiri siguen siendo ARM32. No hay todavía un arranque mainline validado.

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
ni accede al dispositivo. La transición SMC, PSCI/SMP, DTB, periféricos y el
arranque de Linux/OpenWrt siguen pendientes de prueba en hardware.

## GPT

Esta rama no modifica el GPT. Orden acordado:

1. **ARM64 as-is.** Probar con el particionado y el firmware de arranque
   actuales. Solo cambian el payload y la imagen de arranque; se conservan
   nombres y tamaños.
2. **Reclamar espacio sin tocar `vendor`.** Tras validar el arranque, preparar
   `rootfs` de **256 MiB** y aprovechar para `rootfs_data` todo el espacio
   posible al eliminar `recovery` Android y `cache` y reducir `system`.
   `vendor` conserva nombre, posición, tamaño y contenido. Se aceptan huecos
   sin asignar o un layout irregular; no se toca `vendor` para eliminarlos.
3. **Eliminar `vendor` al validar el firmware mainline.** Solo cuando se haya
   comprobado que el firmware disponible para mainline es suficiente para
   el hardware que se vaya a utilizar, y se hayan preservado los blobs/datos
   necesarios, eliminar `vendor` y reajustar el layout para aprovechar su espacio.

La `vendor` de la OTA contiene HAL/bibliotecas Android, módulos del kernel
Android y firmware, entre otros `WIFI_RAM_CODE_MT7663.bin`,
`mt7663_patch_e2_hdr.bin` y `EEPROM_MT7663.bin`. Los módulos Android no sirven
para mainline; los blobs/datos que requieran sus drivers pueden empaquetarse en
el rootfs. `vendor` permanece intacta durante los pasos 1 y 2; su eliminación
queda aplazada al paso 3.

Antes de aplicar el segundo paso hay que adaptar las dependencias actuales:
`lk`, `boot`, `recovery` y `MISC` se buscan por nombre entre las primeras 16
entradas GPT, de 128 bytes desde LBA 2; el instalador también exige `tee1`.
Eliminar `recovery` requiere cambiar el arranque, los flags de MISC y los
instaladores. También se adaptarán el montaje del overlay y sysupgrade de OpenWrt.

Volver a Android requerirá restaurar el GPT y las imágenes Android, además de
Kamakiri: reinstalar Kamakiri por sí solo no reconstruye los datos eliminados.

# Sheldon: GPT para OpenWrt (experimental)

Esta rama incluye un generador de GPT y ZIPs independientes, utilizables desde
BootROM o TWRP. Generar los archivos no modifica la eMMC.
Orden acordado:

1. **ARM64 as-is.** Probar con el particionado y el firmware de arranque
   actuales. Solo cambian el payload y la imagen de arranque; se conservan
   nombres y tamaños.
2. **Reclamar espacio sin tocar `vendor` ni el rescate.** Reducir `system`
   (`/rom`) a **128 MiB**, eliminar `cache` y entregar el espacio a `userdata`
   (`/overlay`): **7129,796 MiB**. `recovery` y las demás particiones conservan
   sus nombres, posiciones, tamaños y GUID. La GPT nueva tiene entradas
   consecutivas: `system` es p11 y `userdata` p12, sin `cache` ni huecos.
   Se conservan los GUID; el montaje debe usar labels, no p13.
3. **Variante preparada sin `vendor`: system de 64 MiB.** `system` pasa a p10,
   LBA 102400..233471; `userdata` a p11, LBA 233472..15273566 (**7343,796 MiB**).
   Se conservan p1..p9 y las labels; no quedan huecos. Su aplicación sigue
   pendiente de validar/preservar el firmware necesario. Solo cuando se haya
   comprobado que el firmware disponible para mainline es suficiente para
   el hardware que se vaya a utilizar, y se hayan preservado los blobs/datos
   necesarios, eliminar `vendor` y reajustar el layout para aprovechar su espacio.

La `vendor` de la OTA contiene HAL/bibliotecas Android, módulos del kernel
Android y firmware, entre otros `WIFI_RAM_CODE_MT7663.bin`,
`mt7663_patch_e2_hdr.bin` y `EEPROM_MT7663.bin`. Los módulos Android no sirven
para mainline; los blobs/datos que requieran sus drivers pueden empaquetarse en
el rootfs. `vendor` permanece intacta durante los pasos 1 y 2; su eliminación
queda aplazada al paso 3.

El segundo paso conserva las dependencias actuales: `lk`, `boot`, `recovery`
y `MISC` se buscan por nombre entre las primeras 16 entradas GPT, de 128 bytes
desde LBA 2; el instalador también exige `tee1`. Eliminar `recovery` en otro
momento requeriría adaptar el arranque, los flags de MISC y los instaladores.

## Generar el GPT y el ZIP

`make-gpt.sh` se ejecuta en OpenWrt con el `sfdisk` ya instalado. Está fijado
al GPT leído de este stick y a su eMMC de 15273600 sectores de 512 bytes;
acepta únicamente tablas verificadas y obtiene los GUID del volcado original.
Los binarios y los instaladores se fijan al perfil de GUID usado al construirlos;
tras restaurar otra GPT hay que regenerar los archivos y revisar los hashes.
Crea una GPT **desde cero**, con una definición completa de 12 particiones
(o 11 en la variante sin vendor),
sobre un archivo disperso vacío: no redimensiona ni reordena una tabla previa.
Conserva el MBR original, nunca escribe la eMMC y exige un directorio de salida nuevo:

```sh
ssh root@192.168.1.1 'sh -s -- /tmp/gpt-openwrt-128' < make-gpt.sh
mkdir -p bin
scp -O -r root@192.168.1.1:/tmp/gpt-openwrt-128 bin/
bash makedist-gpt.sh
```

Los archivos quedan en `bin/gpt-openwrt-128/`:

- `gpt-primary.bin`: 34 sectores, desde LBA 0 (incluye el MBR original).
- `gpt-backup.bin`: 33 sectores, desde LBA 15273567.
- `original-primary.bin` y `original-backup.bin`: copias anteriores.
- `layout.sfdisk`: descripción de la tabla nueva.

El ZIP es `dist/sheldon-gpt-openwrt-128.zip`. No instala LK, preloader ni imágenes
de particiones. Incluye las copias originales del GPT y los payloads SRAM necesarios
para su método BootROM; no ejecuta el instalador completo de Kamakiri.
Comprueba dispositivo, geometría, hashes de los archivos y las dos tablas
actuales; escribe primero el respaldo, verifica su lectura y después escribe
y verifica la primaria. Rechaza particiones afectadas montadas y no formatea.
TWRP extrae nombres exactos (su `unzip` no expande comodines) y usa `toybox dd`:
el `dd` independiente de este recovery no admite los offsets del final de la eMMC.

**En TWRP:** desmontar System, Cache y Data; usar USB o ADB sideload si el ZIP
estaba en Data. Después de flashearlo, **reiniciar recovery antes de borrar o
recrear `userdata`**: el kernel aún puede usar el mapa viejo.
Desde stock cambia su inicio: cambiar el GPT no mueve su ext4. Si solo se pasa
del layout experimental p13 al p12 con los mismos límites, no hace falta formatear. El usuario se encarga
de recrearla; revisar su montaje/etiqueta y la compatibilidad de sysupgrade.
La ROM anterior observada por UART contiene `sheldon-overlay-init`, que rechaza la nueva
geometría con `Stock geometry mismatch`. Ese inicializador también debe adaptarse
al layout/label `userdata`; generar o flashear otra GPT no elimina esa comprobación.

Comprobación reproducible en el host, incluyendo simulación del instalador
sobre un archivo disperso (sin dispositivos reales):

```sh
python3 test_gpt.py bin/gpt-openwrt-128 dist/sheldon-gpt-openwrt-128.zip
```

## Variante de 64 MiB sin vendor

Se conserva la variante anterior de 128 MiB con vendor; no se sobrescriben sus
binarios ni su ZIP. La nueva conserva las labels y los GUID retenidos, pero
**mueve físicamente system y userdata**. La GPT no mueve sus contenidos.
El OpenWrt actualizado por el usuario usa labels, sin depender de UUID ni partno.

Generar (solo lectura de la eMMC, escritura a archivos) y empaquetar:

```sh
sh make-gpt.sh --no-vendor /tmp/gpt-openwrt-64-no-vendor
# Copiar ese directorio al host en bin/ antes de empaquetar.
bash makedist-gpt.sh bin/gpt-openwrt-64-no-vendor
python3 test_gpt.py bin/gpt-openwrt-64-no-vendor dist/sheldon-gpt-openwrt-64-no-vendor.zip
```

Salida: `bin/gpt-openwrt-64-no-vendor/{gpt-primary,gpt-backup}.bin` y
`dist/sheldon-gpt-openwrt-64-no-vendor.zip` (TWRP/BootROM).
Tras flashear, **reiniciar recovery antes de escribir imágenes o recrear Data**;
reflashear OpenWrt system (máximo **67108864 bytes**) y recrear userdata.
El rootfs debe contener el firmware necesario: ya no podrá obtenerlo de vendor.
Desde el repositorio, el flasher BootROM requiere la ruta explícita
`bin/gpt-openwrt-64-no-vendor`; sin ruta conserva el default antiguo de 128 MiB.
Dentro del ZIP, el default apunta a los archivos del propio paquete.

## Variante de 64 MiB con vendor

Conserva p1..p10, incluido vendor de 150 MiB en su posición original. System es
p11, LBA 409600..540671 (64 MiB); userdata es p12, LBA 540672..15273566
(7193.796 MiB). Cache sigue eliminada. Se conservan labels, GUIDs y entradas
consecutivas, sin sobrescribir las otras variantes.

```sh
sh make-gpt.sh --64 /tmp/gpt-openwrt-64
# Copiar al host en bin/ antes de empaquetar.
bash makedist-gpt.sh bin/gpt-openwrt-64
python3 test_gpt.py bin/gpt-openwrt-64 dist/sheldon-gpt-openwrt-64.zip
```

Desde la variante sin vendor, system vuelve de 50 a 200 MiB: la GPT no mueve el
rootfs ni restaura datos de vendor sobrescritos. Reiniciar recovery antes de
escribir imágenes o recrear userdata; el system debe caber en 67108864 bytes.
Existe una copia original de vendor en
`bin/gpt-before-64-no-vendor-20261017-221330/vendor.img` (150 MiB), con su SHA256
verificado contra el manifiesto previo. Restaurar esa imagen es una operación
separada del flasheo GPT. Esta variante permite investigar la dependencia de LK,
pero también cambia el inicio de system: un arranque correcto no demostraría por
sí solo que vendor era la causa del fallo.

## GPT solo por BootROM

```sh
make -C brom-payload stage1/stage1.bin stage2/stage2.bin
sudo ./gpt-bootrom-flash.sh --crash
```

Iniciar el script antes de conectar el stick. `--crash` permite intentar el salto
preloader → BROM solo en RAM; antes de cargar el payload SRAM o escribir se exige
que el dispositivo vuelva a enumerarse en BROM. Sin el flag se requiere BROM
directo; fastboot no es un modo de entrada válido. Reutiliza el exploit y los
payloads en SRAM; no ejecuta `main.py` ni `fixgpt`, que continuarían con la
instalación completa de Kamakiri.

Solo escribe los 33 sectores del respaldo y los 34 de la primaria, en ese orden,
con lectura de verificación antes de continuar. Guarda las tablas anteriores en
`bin/gpt-before-brom-*/`; rechaza otro dispositivo, archivos alterados o una GPT
actual desconocida. No toca boot0, RPMB, LK, preloader, MISC ni recovery; tampoco
formatea ni reinicia. Desconectar/reconectar después para abandonar el payload SRAM.

## Flasheo manual con `dd`

**Solo desde TWRP o un initramfs, sin `system`, `cache` ni `userdata` montadas.**
No ejecutar desde el OpenWrt instalado, que usa `/rom` y `/overlay` en la eMMC.
Este procedimiento exige el GPT original; si una comparación falla, parar.

Desde el host, con TWRP arrancado y ADB conectado:

```sh
python3 test_gpt.py bin/gpt-openwrt-128
adb push bin/gpt-openwrt-128/*.bin /tmp/
adb shell
```

En la shell de TWRP (en un initramfs Linux, cambiar `DEV` a `/dev/mmcblk0`):

```sh
set -eu
cd /tmp
DEV=/dev/block/mmcblk0
command -v toybox >/dev/null # Necesario para los offsets de 64 bits en TWRP.
[ -b "$DEV" ]
read -r sectors < /sys/class/block/mmcblk0/size
read -r sector_size < /sys/class/block/mmcblk0/queue/logical_block_size
[ "$sectors" = 15273600 ] && [ "$sector_size" = 512 ] || exit 1
for part in 11 12 13; do
    node=/sys/class/block/mmcblk0p$part/dev
    if [ ! -f "$node" ]; then
        case "$part" in 12|13) continue ;; esac
        exit 1
    fi
    read -r devnum < "$node"
    mounted=$(awk -v n="$devnum" '$3 == n || $5 ~ /^\/(data|cache|system|system_root|rom|overlay)(\/|$)/ { print $5; exit }' /proc/self/mountinfo)
    [ -z "$mounted" ] || { echo "Desmontar: $mounted"; exit 1; }
done

toybox dd if="$DEV" of=before-primary.bin bs=512 count=34
toybox dd if="$DEV" of=before-backup.bin bs=512 skip=15273567 count=33
cmp original-primary.bin before-primary.bin
cmp original-backup.bin before-backup.bin

# Respaldo primero; no tocar la primaria si falla su escritura o verificación.
toybox dd if=gpt-backup.bin of="$DEV" bs=512 seek=15273567 count=33 conv=notrunc
sync
toybox dd if="$DEV" of=check-backup.bin bs=512 skip=15273567 count=33
cmp gpt-backup.bin check-backup.bin

toybox dd if=gpt-primary.bin of="$DEV" bs=512 count=34 conv=notrunc
sync
toybox dd if="$DEV" of=check-primary.bin bs=512 count=34
cmp gpt-primary.bin check-primary.bin
```

El destino es **el disco eMMC completo**, nunca `mmcblk0boot0` ni una partición
`mmcblk0pN`. Después, **reiniciar recovery antes de recrear `userdata`**.
No se formatea ni se desplaza ningún sistema de archivos con estos comandos.

Volver a Android requerirá restaurar el GPT y las imágenes Android, además de
Kamakiri: reinstalar Kamakiri por sí solo no reconstruye los datos eliminados.

## Relación con el payload ARM64

El ZIP GPT es independiente: `dist/sheldon-gpt-openwrt-128.zip`. También admite
TWRP o BootROM: descomprimir y ejecutar `sudo ./gpt-bootrom-flash.sh --crash`
en su carpeta; omitir el flag si ya se conecta directamente en BROM.
Ambos ZIP incluyen SRAM payloads, módulos y checksums, sin firmware de instalación.
Si se usan ambos, actualizar primero el payload, después GPT y **reiniciar recovery
antes de recrear userdata**. Los README incluidos explican el alcance de cada ZIP.

La actualización del payload se documenta en [ARM64.md](ARM64.md).

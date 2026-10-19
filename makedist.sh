#!/bin/bash

# --payload-only-zip: flashable zip that only updates the lk-payload.
# --gpt-zip: TWRP zip with the GPT images from a make-gpt.sh output dir.
# The default flow below stays the original (stages dist/full from local
# bin/ blobs).
if [ "$1" = "--payload-only-zip" ]; then
    rm -rf dist/lkzip dist/kamakiri-lk-payload.zip
    make -C lk-payload
    mkdir -p dist/lkzip/META-INF/com/google/android dist/lkzip/kamakiri/lk-payload/build
    cp META-INF/com/google/android/update-binary-lk-payload dist/lkzip/META-INF/com/google/android/update-binary
    cp META-INF/com/google/android/updater-script dist/lkzip/META-INF/com/google/android/
    cp lk-payload/build/payload.bin dist/lkzip/kamakiri/lk-payload/build/
    ( cd dist/lkzip && zip -qr -X ../kamakiri-lk-payload.zip META-INF kamakiri )
    rm -rf dist/lkzip
    echo "dist/kamakiri-lk-payload.zip"
    exit 0
fi

if [ "$1" = "--gpt-zip" ]; then
    set -e
    INPUT=${2:-bin/gpt-openwrt-128}
    python3 test_gpt.py "$INPUT"
    if ! grep -q 'name="vendor"' "$INPUT/layout.sfdisk"; then
        NAME=sheldon-gpt-openwrt-64-no-vendor
    elif grep -Eq 'size=[[:space:]]*131072,.*name="system"' "$INPUT/layout.sfdisk"; then
        NAME=sheldon-gpt-openwrt-64
    else
        NAME=sheldon-gpt-openwrt-128
    fi
    STAGE=$(mktemp -d)
    trap 'rm -rf "$STAGE"' EXIT
    mkdir -p "$STAGE/META-INF/com/google/android" "$STAGE/gpt" dist
    for file in gpt-primary.bin gpt-backup.bin original-primary.bin original-backup.bin layout.sfdisk original.sfdisk; do
        cp "$INPUT/$file" "$STAGE/gpt/"
    done
    cp gpt/README.txt "$STAGE/gpt/"
    sha() { sha256sum "$INPUT/$1" | cut -d' ' -f1; }
    sed -e "s/__PRIMARY_SHA256__/$(sha gpt-primary.bin)/g" \
        -e "s/__BACKUP_SHA256__/$(sha gpt-backup.bin)/g" \
        -e "s/__ORIGINAL_PRIMARY_SHA256__/$(sha original-primary.bin)/g" \
        -e "s/__ORIGINAL_BACKUP_SHA256__/$(sha original-backup.bin)/g" \
        META-INF/com/google/android/update-binary-gpt > "$STAGE/META-INF/com/google/android/update-binary"
    chmod 755 "$STAGE/META-INF/com/google/android/update-binary"
    cp META-INF/com/google/android/updater-script "$STAGE/META-INF/com/google/android/"
    ( cd "$STAGE" && zip -qr "$OLDPWD/dist/$NAME.zip" META-INF gpt )
    rm -rf "$STAGE"; trap - EXIT
    python3 test_gpt.py "$INPUT" "dist/$NAME.zip"
    echo "dist/$NAME.zip ready (GPT only, no filesystems formatted)"
    exit 0
fi

rm -rf dist

mkdir -p dist/unlock/kamakiri/bin
cp bin/{preloader.img,lk.bin,tz.img,twrp.img,microloader.bin} dist/unlock/kamakiri/bin/

mkdir -p dist/unlock/kamakiri/lk-payload/build
cp lk-payload/build/payload.bin dist/unlock/kamakiri/lk-payload/build/

mkdir -p dist/unlock/kamakiri/modules
cp modules/{common.py,load_payload.py,logger.py,main.py,functions.py,handshake2.py} dist/unlock/kamakiri/modules/

mkdir -p dist/unlock/kamakiri/brom-payload/stage1
cp brom-payload/stage1/stage1.bin dist/unlock/kamakiri/brom-payload/stage1/

mkdir -p dist/unlock/kamakiri/brom-payload/stage2
cp brom-payload/stage2/stage2.bin dist/unlock/kamakiri/brom-payload/stage2/

mkdir -p dist/unlock/kamakiri/brom-payload/pl
cp brom-payload/pl/pl.bin dist/unlock/kamakiri/brom-payload/pl/

cp {bootrom-step.sh,fastboot-step.sh,boot-recovery.sh,boot-fastboot.sh} dist/unlock/kamakiri/

mkdir -p dist/unlock/META-INF/com/google/android
cp META-INF/com/google/android/{update-binary,updater-script} dist/unlock/META-INF/com/google/android/

#mkdir -p dist/stock/kamakiri/bin
#cp bin/{boot.img,recovery.img} dist/stock/kamakiri/bin/
#cp return-to-stock.sh dist/stock/kamakiri/

mkdir -p dist/gptfix/kamakiri/bin
cp gpt-fix.sh dist/gptfix/kamakiri/
cp bin/gpt-sheldon.bin dist/gptfix/kamakiri/bin/

mkdir -p dist/full
cp -r dist/unlock/* dist/full/
#cp -r dist/stock/* dist/full/
cp -r dist/gptfix/* dist/full/

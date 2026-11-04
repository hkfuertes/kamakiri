#!/bin/bash

# Flashable zip that only updates the lk-payload; the default flow below
# stays the original (stages dist/full from local bin/ blobs).
# The OpenWrt GPT project lives in gpt/ with its own makedist.sh.
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

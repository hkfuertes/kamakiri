# Flashable zip that only updates the lk-payload on mmcblk0boot0.
# Full dist (TWRP, preloader, tz, ...) is still built by makedist.sh.

LK_ZIP = dist/kamakiri-lk-payload.zip

.PHONY: lk-payload-zip
lk-payload-zip: $(LK_ZIP)

lk-payload/build/payload.bin:
	$(MAKE) -C lk-payload

$(LK_ZIP): lk-payload/build/payload.bin \
		META-INF/com/google/android/update-binary-lk-payload \
		META-INF/com/google/android/updater-script
	rm -rf dist/lkzip
	mkdir -p dist/lkzip/META-INF/com/google/android dist/lkzip/kamakiri/lk-payload/build
	cp META-INF/com/google/android/update-binary-lk-payload dist/lkzip/META-INF/com/google/android/update-binary
	cp META-INF/com/google/android/updater-script dist/lkzip/META-INF/com/google/android/
	cp lk-payload/build/payload.bin dist/lkzip/kamakiri/lk-payload/build/
	cd dist/lkzip && zip -qr -X ../kamakiri-lk-payload.zip META-INF kamakiri
	rm -rf dist/lkzip
	@echo "$(LK_ZIP)"

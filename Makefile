# Flashable zips.
# - full-zip: the original master zip (TWRP, boot patch, preloader, payload, tz)
#   built by makedist.sh from dist/full. Needs bin/ artifacts and brom-payload
#   built beforehand.
# - lk-payload-zip: only updates the lk-payload on mmcblk0boot0.
# Note: makedist.sh wipes dist/, so build one zip or the other per run.

LK_ZIP = dist/kamakiri-lk-payload.zip

.PHONY: full-zip
full-zip:
	./makedist.sh
	cd dist/full && zip -qr -X ../kamakiri-full.zip META-INF kamakiri
	@echo "dist/kamakiri-full.zip"

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

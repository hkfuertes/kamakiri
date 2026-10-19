# Our zip: flashable, only updates the lk-payload on mmcblk0boot0.
# The original full master zip is NOT built here — makedist.sh keeps its
# original behavior (stages dist/full from local bin/ blobs that can't
# live on github; zip it yourself on a machine that has them).

LK_ZIP = dist/kamakiri-lk-payload.zip

.PHONY: lk-payload-zip lk-payload/build/payload.bin
lk-payload-zip: $(LK_ZIP)

# phony so source edits always reach the sub-make's own dependency tracking
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

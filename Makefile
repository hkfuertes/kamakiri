# Convenience wrapper; the logic lives in makedist.sh.
# Default makedist.sh behavior (full master zip staging) is untouched.

.PHONY: lk-payload-zip
lk-payload-zip:
	./makedist.sh --payload-only-zip

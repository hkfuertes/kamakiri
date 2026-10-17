#!/bin/bash
# Existing Kamakiri only: never run the full bootrom-step/main.py installer.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -u modules/boot0_flash.py "$@"

#!/bin/bash
# GPT only: never invoke main.py/fixgpt (the full Kamakiri installer).
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -u modules/gpt_flash.py "$@"

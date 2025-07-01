#!/bin/bash
set -euo pipefail

export PYTHONPATH="/app:${PYTHONPATH:-}"

if [ "$1" == "pip" ]; then
    shift
    exec pip "$@"
else
    exec python3 -m tarawasm.cli "$@"
fi

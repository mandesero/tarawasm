#!/bin/bash
set -euo pipefail

export PYTHONPATH="/app:${PYTHONPATH:-}"

if [ "${1:-}" == "pip" ]; then
    shift
    exec pip "$@"
fi

# Allow explicit tools/commands inside the container.
if [ "${1:-}" == "wasmtime" ] || [ "${1:-}" == "python3" ] || [ "${1:-}" == "pytest" ] || [ "${1:-}" == "bash" ] || [ "${1:-}" == "sh" ]; then
    exec "$@"
fi

exec python3 -m tarawasm.cli "$@"

#!/usr/bin/env bash
set -euo pipefail
# Run as the intended user: managed tools are stored in their data directory.
python3 -m tarawasm.cli toolchain setup --all --mode local --install --yes "$@"

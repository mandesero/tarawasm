#!/usr/bin/env bash

set -euo pipefail

# Build standalone binary
nuitka \
    --onefile \
    --standalone \
    --include-package=tarawasm.backends \
    --output-dir=target \
    --output-filename=tarawasm \
    --include-data-dir=tarawasm/lang_deps=tarawasm/lang_deps \
    tarawasm/cli.py

echo "Build complete. Generated './tarawasm' binary."

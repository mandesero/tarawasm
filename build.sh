#!/usr/bin/env bash

set -euo pipefail

# Build standalone binary
nuitka --onefile --standalone tarawasm.py -o tarawasm

echo "Build complete. Generated './tarawasm' binary."

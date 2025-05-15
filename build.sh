#!/usr/bin/env bash

set -euo pipefail

# Install build dependencies
pip install nuitka

# Build standalone binary
nuitka --onefile --standalone tarawasm.py -o tarawasm

echo "Build complete. Generated './tarawasm' binary."

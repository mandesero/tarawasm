#!/bin/bash
set -euo pipefail

# System dependencies
if command -v apt-get &> /dev/null; then
    sudo apt-get update
    sudo apt-get install -y \
        build-essential \
        ca-certificates \
        cmake \
        curl \
        git \
        gnupg \
        lld \
        llvm \
        patchelf \
        python3 \
        python3-dev \
        python3-pip \
        wget
fi

# Install Go 1.24.3
GO_VERSION=1.24.3
GO_HASH=3333f6ea53afa971e9078895eaa4ac7204a8c6b5c68c10e6bc9a33e8e391bdd8
if ! command -v go &> /dev/null || [[ "$(go version | awk '{print $3}')" != "go${GO_VERSION}" ]]; then
    wget -q "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz"
    echo "${GO_HASH}  go${GO_VERSION}.linux-amd64.tar.gz" | sha256sum -c
    sudo rm -rf /usr/local/go && sudo tar -C /usr/local -xzf "go${GO_VERSION}.linux-amd64.tar.gz"
    rm "go${GO_VERSION}.linux-amd64.tar.gz"
fi

# Install Rust
if ! command -v rustup &> /dev/null; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    # shellcheck source=/dev/null
    source "$HOME/.cargo/env"
fi

# Install TinyGo
TINYGO_VERSION=0.37.0
TINYGO_HASH=8f34a4aac7f1aa2ad51dc0f4eccd40da13b6f52fbac5c13887d57327e5f0a862
if ! command -v tinygo &> /dev/null; then
    wget -q "https://github.com/tinygo-org/tinygo/releases/download/v${TINYGO_VERSION}/tinygo_${TINYGO_VERSION}_amd64.deb"
    echo "${TINYGO_HASH}  tinygo_${TINYGO_VERSION}_amd64.deb" | sha256sum -c
    sudo dpkg -i "tinygo_${TINYGO_VERSION}_amd64.deb"
    rm "tinygo_${TINYGO_VERSION}_amd64.deb"
fi

# Python dependencies
pip3 install -r requirements.txt

# WASM tools
cargo install --locked --root /usr/local wkg --version 0.10.0
cargo install --locked --root /usr/local wasm-tools
cargo install --locked --root /usr/local cargo-component --version 0.21.1
cargo install --locked --root /usr/local wit-bindgen-cli

# Node.js
if command -v apt-get &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

# JavaScript tools
npm install -g \
    @bytecodealliance/jco@1.9.1 \
    @bytecodealliance/componentize-js

# wasi-sdk
if ! clang --version | grep -q "Target: wasm32-unknown-wasi"; then
    echo "Installing wasi-sdk"
    wget -q https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-25/wasi-sdk-25.0-x86_64-linux.deb
    sudo apt install -y "./wasi-sdk-25.0-x86_64-linux.deb"
    rm "wasi-sdk-25.0-x86_64-linux.deb"
    
    # Add /opt/wasi-sdk/bin to PATH for this session
    export WASI_SDK_PATH=/opt/wasi-sdk
    export PATH=$WASI_SDK_PATH/bin:$PATH
    echo "export WASI_SDK_PATH=\"/opt/wasi-sdk\"" >> ~/.bashrc
    echo "export PATH=\"/opt/wasi-sdk/bin:\$PATH\"" >> ~/.bashrc
fi

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

# Install Go 1.26.0
GO_VERSION=1.26.0
GO_HASH=aac1b08a0fb0c4e0a7c1555beb7b59180b05dfc5a3d62e40e9de90cd42f88235
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
rustup update stable
rustup default stable

# Install TinyGo
TINYGO_VERSION=0.40.1
TINYGO_HASH=a01268e1926225feebfb3b81bd33237cd8d6e42e7915221638690b3a41f7647c
if ! command -v tinygo &> /dev/null || [[ "$(tinygo version | awk '{print $3}')" != "${TINYGO_VERSION}" ]]; then
    wget -q "https://github.com/tinygo-org/tinygo/releases/download/v${TINYGO_VERSION}/tinygo_${TINYGO_VERSION}_amd64.deb"
    echo "${TINYGO_HASH}  tinygo_${TINYGO_VERSION}_amd64.deb" | sha256sum -c
    sudo dpkg -i "tinygo_${TINYGO_VERSION}_amd64.deb"
    rm "tinygo_${TINYGO_VERSION}_amd64.deb"
fi

# Python dependencies
pip3 install -r requirements.txt

# WASM tools
cargo install --locked --root /usr/local wkg --version 0.15.0
cargo install --locked --root /usr/local wasm-tools --version 1.245.1
cargo install --locked --root /usr/local cargo-component --version 0.21.1
cargo install --locked --root /usr/local wit-bindgen-cli --version 0.53.1

# Node.js
if command -v apt-get &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

# JavaScript tools
npm install -g \
    @bytecodealliance/jco@1.17.0 \
    @bytecodealliance/componentize-js@0.19.3 \
    @bytecodealliance/preview2-shim@0.17.8

# wasi-sdk
if ! clang --version | grep -q "Target: wasm32-unknown-wasi"; then
    echo "Installing wasi-sdk"
    WASI_SDK_VERSION=30.0
    WASI_SDK_FILENAME="wasi-sdk-${WASI_SDK_VERSION}-x86_64-linux.deb"
    WASI_SDK_HASH=c714f7894a25475aa9be5244b6a20987f18b05b2e9e127677db141d61220df7b
    wget -q "https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-30/${WASI_SDK_FILENAME}"
    echo "${WASI_SDK_HASH}  ${WASI_SDK_FILENAME}" | sha256sum -c
    sudo apt install -y "./${WASI_SDK_FILENAME}"
    rm "${WASI_SDK_FILENAME}"
    
    # Add /opt/wasi-sdk/bin to PATH for this session
    export WASI_SDK_PATH=/opt/wasi-sdk
    export PATH=$WASI_SDK_PATH/bin:$PATH
    echo "export WASI_SDK_PATH=\"/opt/wasi-sdk\"" >> ~/.bashrc
    echo "export PATH=\"/opt/wasi-sdk/bin:\$PATH\"" >> ~/.bashrc
fi

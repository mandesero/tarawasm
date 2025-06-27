FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app
COPY . .

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-dev build-essential \
    curl wget git ca-certificates gnupg \
    patchelf \
    golang-go \
    llvm clang lld cmake \
    && rm -rf /var/lib/apt/lists/*

# Install Go manually
RUN rm -rf /usr/local/go && \
    curl -L https://go.dev/dl/go1.24.3.linux-amd64.tar.gz -o go.tar.gz && \
    tar -C /usr/local -xzf go.tar.gz && \
    rm go.tar.gz
ENV PATH="/usr/local/go/bin:${PATH}"

# Install Rust
RUN curl https://sh.rustup.rs -sSf | bash -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Install TinyGo
RUN curl -L https://github.com/tinygo-org/tinygo/releases/download/v0.37.0/tinygo_0.37.0_amd64.deb -o tinygo.deb && \
    dpkg -i tinygo.deb && \
    rm tinygo.deb

# Python deps
RUN pip3 install --no-cache-dir -r requirements.txt

# WASM tools
RUN cargo install wkg wasm-tools cargo-component wit-bindgen-cli

# Node.js 22.x
RUN apt-get remove -y nodejs npm libnode-dev || true && \
    apt-get autoremove -y && \
    apt-get clean && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs=22.* && \
    rm -rf /var/lib/apt/lists/*

# JS tooling
RUN npm install -g @bytecodealliance/jco@latest @bytecodealliance/componentize-js@latest

# WASI SDK
RUN curl -L https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-25/wasi-sdk-25.0-x86_64-linux.deb -o wasi.deb && \
    apt-get install -y --no-install-recommends ./wasi.deb && \
    rm wasi.deb && \
    rm -rf /var/lib/apt/lists/*
ENV WASI_SDK_PATH=/opt/wasi-sdk
ENV PATH="${WASI_SDK_PATH}/bin:${PATH}"

# Nuitka build
RUN nuitka \
    --onefile \
    --standalone \
    --include-package=tarawasm.templates \
    --output-dir=target \
    --output-filename=tarawasm \
    --include-data-dir=tarawasm/templates=tarawasm/templates \
    --include-data-dir=tarawasm/lang_deps=tarawasm/lang_deps \
    tarawasm/cli.py

ENTRYPOINT ["/app/docker-scripts/entrypoint.sh"]
CMD ["--help"]

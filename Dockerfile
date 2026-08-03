FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-dev build-essential \
    curl wget git ca-certificates gnupg util-linux \
    patchelf \
    golang-go \
    llvm clang lld cmake \
    && rm -rf /var/lib/apt/lists/*

# Install Go manually
RUN rm -rf /usr/local/go && \
    curl -L https://go.dev/dl/go1.25.6.linux-amd64.tar.gz -o go.tar.gz && \
    tar -C /usr/local -xzf go.tar.gz && \
    rm go.tar.gz
ENV PATH="/usr/local/go/bin:${PATH}"

# Install Rust in a location available to the runtime UID selected by the entrypoint.
ENV RUSTUP_HOME=/opt/rustup
ENV CARGO_HOME=/opt/cargo
RUN curl https://sh.rustup.rs -sSf | bash -s -- -y
ENV PATH="${CARGO_HOME}/bin:${PATH}"

# Install TinyGo
RUN curl -L https://github.com/tinygo-org/tinygo/releases/download/v0.40.1/tinygo_0.40.1_amd64.deb -o tinygo.deb && \
    dpkg -i tinygo.deb && \
    rm tinygo.deb

# WASM tools
RUN cargo install --locked wkg --version 0.15.0 && \
    cargo install --locked wasm-tools --version 1.245.1 && \
    cargo install --locked cargo-component --version 0.21.1 && \
    cargo install --locked wit-bindgen-cli --version 0.53.1
RUN rustup target add wasm32-wasip1

# Node.js 24.x (LTS)
RUN apt-get remove -y nodejs npm libnode-dev || true && \
    apt-get autoremove -y && \
    apt-get clean && \
    curl -fsSL https://deb.nodesource.com/setup_24.x | bash - && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs=24.* && \
    rm -rf /var/lib/apt/lists/*

# JS tooling
RUN npm install -g \
    @bytecodealliance/jco@1.17.0 \
    @bytecodealliance/componentize-js@0.19.3 \
    @bytecodealliance/preview2-shim@0.17.8

# WASI SDK
RUN curl -L https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-30/wasi-sdk-30.0-x86_64-linux.deb -o wasi.deb && \
    apt-get install -y --no-install-recommends ./wasi.deb && \
    rm wasi.deb && \
    rm -rf /var/lib/apt/lists/*
ENV WASI_SDK_PATH=/opt/wasi-sdk
ENV PATH="${WASI_SDK_PATH}/bin:${PATH}"

# Wasm runtime for in-container execution in tests
RUN curl https://wasmtime.dev/install.sh -sSf | bash && \
    mv /root/.wasmtime/bin/wasmtime /usr/local/bin/wasmtime && \
    rm -rf /root/.wasmtime

COPY . .

ENV INSIDE_DOCKER=1

# Python deps
RUN pip3 install --no-cache-dir -r requirements.txt

RUN chmod +x /app/docker-scripts/entrypoint.sh

ENTRYPOINT ["/app/docker-scripts/entrypoint.sh"]
CMD ["--help"]

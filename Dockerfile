FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-dev build-essential \
    curl gnupg wget git ca-certificates \
    patchelf \
    golang-go \
    llvm clang lld cmake \
    && rm -rf /var/lib/apt/lists/*

# Install Go 1.24.3 manually (remove old Go if any)
RUN rm -rf /usr/local/go && \
    wget https://go.dev/dl/go1.24.3.linux-amd64.tar.gz && \
    tar -C /usr/local -xzf go1.24.3.linux-amd64.tar.gz && \
    rm go1.24.3.linux-amd64.tar.gz

ENV PATH="/usr/local/go/bin:${PATH}"

# Install Rust via rustup
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Install TinyGo
RUN wget https://github.com/tinygo-org/tinygo/releases/download/v0.37.0/tinygo_0.37.0_amd64.deb && \
    dpkg -i tinygo_0.37.0_amd64.deb && \
    rm tinygo_0.37.0_amd64.deb

# Install Python dependencies
RUN pip3 install --no-cache-dir nuitka componentize-py click

# Install WASM tools: wkg, wasm-tools, wit-bindgen
RUN cargo install wkg wasm-tools cargo-component

# Remove old nodejs if installed
RUN apt-get remove -y nodejs npm libnode-dev || true

# Install Node.js 22.x from official source
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
RUN apt-get update && apt-get install -y nodejs

# Install JavaScript tooling: jco and componentize-js globally via npm
RUN npm install -g @bytecodealliance/jco @bytecodealliance/componentize-js

# Set working directory inside the container
WORKDIR /app

# Copy tarawasm.py script into the container
COPY tarawasm.py .

# Build standalone binary with Nuitka
RUN nuitka --onefile --standalone tarawasm.py -o tarawasm && chmod +x tarawasm

# Set entrypoint to the tarawasm binary
ENTRYPOINT ["/app/tarawasm"]
CMD ["--help"]

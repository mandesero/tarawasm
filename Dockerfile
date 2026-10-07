FROM ubuntu:22.04 AS toolchain-builder

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

COPY tarawasm/toolchains/catalog.json /app/toolchain-catalog.json

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-dev build-essential \
    curl wget git ca-certificates gnupg util-linux \
    patchelf \
    llvm clang lld cmake \
    && rm -rf /var/lib/apt/lists/*

# Install Go manually
RUN go_version=$(python3 -c 'import json; print(json.load(open("toolchain-catalog.json"))["tools"]["go"]["recommended"])') && \
    rm -rf /usr/local/go && \
    curl -fL "https://go.dev/dl/go${go_version}.linux-amd64.tar.gz" -o go.tar.gz && \
    tar -C /usr/local -xzf go.tar.gz && \
    rm go.tar.gz
ENV PATH="/usr/local/go/bin:${PATH}"

# Install Rust in a location available to the runtime UID selected by the entrypoint.
ENV RUSTUP_HOME=/opt/rustup
ENV CARGO_HOME=/opt/cargo
RUN curl https://sh.rustup.rs -sSf | bash -s -- -y --profile minimal --default-toolchain "$(python3 -c 'import json; print(json.load(open("toolchain-catalog.json"))["tools"]["rustc"]["recommended"])')"
ENV PATH="${CARGO_HOME}/bin:${PATH}"

# Install TinyGo
RUN tinygo_version=$(python3 -c 'import json; print(json.load(open("toolchain-catalog.json"))["tools"]["tinygo"]["recommended"])') && \
    curl -fL "https://github.com/tinygo-org/tinygo/releases/download/v${tinygo_version}/tinygo_${tinygo_version}_amd64.deb" -o tinygo.deb && \
    dpkg -i tinygo.deb && \
    rm tinygo.deb

# WASM tools
RUN python3 -c 'import json,subprocess; c=json.load(open("toolchain-catalog.json")); [subprocess.run(["cargo","install","--locked",c["tools"][n]["package"],"--version",c["tools"][n]["recommended"]],check=True) for n in ("wkg","wasm-tools","cargo-component","wit-bindgen")]'
RUN rustup target add wasm32-wasip1

# Node.js from the same pinned catalog used by native installation.
RUN node_version=$(python3 -c 'import json; print(json.load(open("toolchain-catalog.json"))["tools"]["node"]["recommended"])') && \
    curl -fL "https://nodejs.org/dist/v${node_version}/node-v${node_version}-linux-x64.tar.gz" -o node.tar.gz && \
    mkdir -p /opt/node && tar -C /opt/node --strip-components=1 -xzf node.tar.gz && rm node.tar.gz
ENV PATH="/opt/node/bin:${PATH}"

# JS tooling
RUN python3 -c 'import json,subprocess; c=json.load(open("toolchain-catalog.json")); names=("jco","componentize-js","preview2-shim"); subprocess.run(["npm","install","-g","--prefix","/usr"]+[c["tools"][n]["package"]+"@"+c["tools"][n]["recommended"] for n in names],check=True); from pathlib import Path; roots=[p.parent for p in Path("/usr/lib/node_modules").rglob("componentize-js*/package.json") if json.loads(p.read_text()).get("name")=="@bytecodealliance/componentize-js"]; [subprocess.run(["npm","install","--prefix",str(p),"--save-prod","--save-exact","--omit=dev","--package-lock=false","--ignore-scripts","@bytecodealliance/preview2-shim@"+c["packages"]["preview2-shim"]],check=True) for p in roots if p.is_dir()]'

# WASI SDK
RUN sdk_version=$(python3 -c 'import json; print(json.load(open("toolchain-catalog.json"))["tools"]["clang"]["install_version"])') && \
    curl -fL "https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-${sdk_version%%.*}/wasi-sdk-${sdk_version}-x86_64-linux.deb" -o wasi.deb && \
    apt-get install -y --no-install-recommends ./wasi.deb && \
    rm wasi.deb && \
    rm -rf /var/lib/apt/lists/*
ENV WASI_SDK_PATH=/opt/wasi-sdk
ENV PATH="${WASI_SDK_PATH}/bin:${PATH}"

# Wasm runtime for in-container execution in tests
RUN curl https://wasmtime.dev/install.sh -sSf | bash -s -- --version "v$(python3 -c 'import json; print(json.load(open("toolchain-catalog.json"))["packages"]["wasmtime"])')" && \
    mv /root/.wasmtime/bin/wasmtime /usr/local/bin/wasmtime && \
    rm -rf /root/.wasmtime

COPY tarawasm /app/tarawasm
COPY docker-scripts /app/docker-scripts
COPY scripts /app/scripts
COPY tests /app/tests
COPY examples /app/examples
COPY requirements*.txt Makefile pyproject.toml /app/

ENV INSIDE_DOCKER=1
ENV TARAWASM_TOOLCHAIN_LANGUAGE=all

# Python deps
RUN pip3 install --no-cache-dir -r requirements.txt && \
    pip3 install --no-cache-dir "componentize-py==$(python3 -c 'import json; print(json.load(open("toolchain-catalog.json"))["tools"]["componentize-py"]["recommended"])')"

RUN chmod +x /app/docker-scripts/entrypoint.sh

ENTRYPOINT ["/app/docker-scripts/entrypoint.sh"]
CMD ["--help"]

# The compiler/tool installer above is shared by all final targets. Its build
# caches and unrelated languages are never copied into a language image.
FROM ubuntu:22.04 AS base
ENV DEBIAN_FRONTEND=noninteractive INSIDE_DOCKER=1 TARAWASM_TOOLCHAIN_LANGUAGE=base
WORKDIR /app
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip ca-certificates libssl3 util-linux \
    && rm -rf /var/lib/apt/lists/*
COPY --from=toolchain-builder /opt/cargo/bin/wasm-tools /usr/local/bin/wasm-tools
COPY --from=toolchain-builder /opt/cargo/bin/wkg /usr/local/bin/wkg
COPY tarawasm /app/tarawasm
COPY docker-scripts /app/docker-scripts
RUN pip3 install --no-cache-dir "click==$(python3 -c 'import json; print(json.load(open("tarawasm/toolchains/catalog.json"))["packages"]["click"])')" && chmod +x /app/docker-scripts/entrypoint.sh
ENTRYPOINT ["/app/docker-scripts/entrypoint.sh"]
CMD ["--help"]

FROM base AS python
ENV TARAWASM_TOOLCHAIN_LANGUAGE=python
RUN pip3 install --no-cache-dir "componentize-py==$(python3 -c 'import json; print(json.load(open("tarawasm/toolchains/catalog.json"))["tools"]["componentize-py"]["recommended"])')"

FROM base AS js
ENV TARAWASM_TOOLCHAIN_LANGUAGE=js
COPY --from=toolchain-builder /opt/node /opt/node
ENV PATH="/opt/node/bin:${PATH}"
COPY --from=toolchain-builder /usr/lib/node_modules /usr/lib/node_modules
RUN python3 -c 'import json; from pathlib import Path; p=Path("/usr/lib/node_modules/@bytecodealliance/jco"); Path("/usr/local/bin/jco").symlink_to(p/json.loads((p/"package.json").read_text())["bin"]["jco"])'

FROM base AS go
ENV TARAWASM_TOOLCHAIN_LANGUAGE=go
COPY --from=toolchain-builder /usr/local/go /usr/local/go
COPY --from=toolchain-builder /usr/local/lib/tinygo /usr/local/lib/tinygo
ENV PATH="/usr/local/go/bin:/usr/local/lib/tinygo/bin:${PATH}"
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

FROM base AS rust
ENV TARAWASM_TOOLCHAIN_LANGUAGE=rust RUSTUP_HOME=/opt/rustup CARGO_HOME=/opt/cargo
COPY --from=toolchain-builder /opt/rustup /opt/rustup
COPY --from=toolchain-builder /opt/cargo/bin /opt/cargo/bin
ENV PATH="/opt/cargo/bin:${PATH}"
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev git \
    && rm -rf /var/lib/apt/lists/*

FROM base AS c
ENV TARAWASM_TOOLCHAIN_LANGUAGE=c WASI_SDK_PATH=/opt/wasi-sdk
COPY --from=toolchain-builder /opt/wasi-sdk /opt/wasi-sdk
COPY --from=toolchain-builder /opt/cargo/bin/wit-bindgen /usr/local/bin/wit-bindgen
ENV PATH="/opt/wasi-sdk/bin:${PATH}"

# Preserve the full toolchain/test image as the default for existing users.
FROM toolchain-builder AS all

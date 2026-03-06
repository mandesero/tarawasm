# tarawasm

A simple CLI for WebAssembly component workflow.

## Supported guest languages

- **Python**
- **Go**
- **Rust**
- **JavaScript**
- **C/C++**

---

## Table of Contents

- [Quickstart](#quickstart)
- [Manual installation](#manual-installation)
  - [1. System packages (Debian/Ubuntu)](#1-system-packages-debianubuntu)
  - [2. Go 1.26.0](#2-go-1260)
  - [3. Rust](#3-rust)
  - [4. TinyGo](#4-tinygo)
  - [5. Python packages](#5-python-packages)
  - [6. WASM tools (Cargo)](#6-wasm-tools-cargo)
  - [7. Node.js 24.x](#7-nodejs-24x)
  - [8. JavaScript tools (npm)](#8-javascript-tools-npm)
  - [9. WASI SDK](#9-wasi-sdk)
- [Using Docker](#using-docker)
- [Usage](#usage)
  - [Providing WIT definitions](#providing-wit-definitions)
  - [Initializing a project](#initializing-a-project)
  - [Generating bindings](#generating-bindings)
  - [Building the WASM component](#building-the-wasm-component)
- [Available Commands](#available-commands)
- [Formatting and linting](#formatting-and-linting)
- [Running tests](#running-tests)

---

## Quickstart

1. **Install everything automatically**

```bash
make install
```

This will:

* Install system packages (via `apt-get`)
* Install Go 1.26.0
* Install Rust (via `rustup`)
* Install TinyGo 0.40.1
* Install Python packages from `requirements.txt`
* Install WASM tools (`wkg`, `wasm-tools`, `cargo-component`, `wit-bindgen-cli`)
* Install Node.js 24.x and JS tools (`jco`, `componentize-js`)

2. **Verify your setup**

```bash
make check
```

Runs both:

* `make system-check` — checks Go, Rust, TinyGo, Node.js, Python, clang (wasi-sdk)
* `make sdk-check` — checks installed CLI tools (`jco`, `componentize-js`, `wkg`, `wasm-tools`, `cargo-component`, `wit-bindgen`) and Python packages

3. **Build your project**

```bash
make build
```

---

## Manual installation

If you prefer to install dependencies manually, follow these steps.

### 1. System packages (Debian/Ubuntu)

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential ca-certificates cmake curl git gnupg \
  lld llvm patchelf python3 python3-dev python3-pip wget
```

### 2. Go 1.26.0

```bash
wget https://go.dev/dl/go1.26.0.linux-amd64.tar.gz
sudo rm -rf /usr/local/go
sudo tar -C /usr/local -xzf go1.26.0.linux-amd64.tar.gz
rm go1.26.0.linux-amd64.tar.gz
export PATH="/usr/local/go/bin:$PATH"
```

### 3. Rust

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
. "$HOME/.cargo/env"
rustup update stable
rustup default stable
```

### 4. TinyGo

```bash
wget https://github.com/tinygo-org/tinygo/releases/download/v0.40.1/tinygo_0.40.1_amd64.deb
sudo dpkg -i tinygo_0.40.1_amd64.deb
rm tinygo_0.40.1_amd64.deb
```

### 5. Python packages

```bash
python3 -m pip install --upgrade pip
python3 -m pip install --no-cache-dir -r requirements.txt
```

### 6. WASM tools (Cargo)

```bash
cargo install --locked --root /usr/local wkg --version 0.15.0
cargo install --locked --root /usr/local wasm-tools --version 1.245.1
cargo install --locked --root /usr/local cargo-component --version 0.21.1
cargo install --locked --root /usr/local wit-bindgen-cli --version 0.53.1
```

### 7. Node.js 24.x

```bash
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### 8. JavaScript tools (npm)

```bash
npm install -g @bytecodealliance/jco@1.17.0 \
               @bytecodealliance/componentize-js@0.19.3
```

### 9. WASI SDK

```bash
wget -q https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-30/wasi-sdk-30.0-x86_64-linux.deb
sudo apt install -y ./wasi-sdk-30.0-x86_64-linux.deb
rm wasi-sdk-30.0-x86_64-linux.deb

# Add /opt/wasi-sdk/bin to PATH
export WASI_SDK_PATH=/opt/wasi-sdk
export PATH=$WASI_SDK_PATH/bin:$PATH
```

---

## Using Docker

You can avoid installing all dependencies locally by using the [official Docker image](https://hub.docker.com/r/mandeser0/tarawasm):

```bash
docker pull mandeser0/tarawasm:latest
```

### Convenient alias

Add this alias to your shell config (`~/.bashrc` or `~/.zshrc`):

```bash
alias tarawasm='docker run --rm -v "$PWD":/work -w /work mandeser0/tarawasm'
```

### Installing additional Python packages inside the Docker container

When working on **Python-based components**, the base Docker image may not include all Python libraries you need.
If you encounter missing dependencies, you can install them directly inside the container using:

```bash
tarawasm pip install <your-package>
```

By default, `tarawasm pip install ...` stores packages in `./.tarawasm/site-packages` (inside your mounted project directory), so they remain available across `--rm` container runs and for subsequent `tarawasm build` commands.

You can override this location with:

```bash
TARAWASM_PY_SITE_PACKAGES=/work/.custom-python-site tarawasm pip install <your-package>
```

---

## Usage

### Providing WIT definitions

Before starting, you need WIT definitions. Example:

```bash
wkg wit build --wit-dir=<path-to-your-wit-files>
```

Move the resulting `.wasm` file into your project directory.

---

### Initializing a project

```bash
tarawasm init --lang <language> --wasm-file <your-wasm-file> <world-name>
```

You can optionally specify a custom source file:

```bash
tarawasm init --lang <language> --wasm-file <your-wasm-file> \
  --src-file <your-source-file> <world-name>
```

### Generating bindings

```bash
tarawasm bind
```

Common overrides (for one run only):

```bash
tarawasm bind --world <world> --wit <wit-path>
```

Language-specific options are passed separately after `--`:

```bash
tarawasm bind --world <world> -- --tool-specific-flag value
```

### Building the WASM component

```bash
tarawasm build
```

Common overrides (for one run only):

```bash
tarawasm build --world <world> --src <src-file> --wit <wit-path> --out <output.wasm> --clean
```

Language-specific options are passed separately after `--`:

```bash
tarawasm build --out <output.wasm> -- --tool-specific-flag value
```

## Available Commands

| Command          | Description                                 |
| ---------------- | --------------------------------------------|
| `tarawasm init`  | Initialize project and save config          |
| `tarawasm bind`  | Generate bindings from WIT                  |
| `tarawasm build` | Compile source to WASM component            |
| `tarawasm clean` | Remove build artifacts                      |
| `tarawasm all`   | Run clean, bind, and build                  |
| `tarawasm strip` | Remove custom sections from the WASM binary |

> The `strip` command helps reduce the size of the generated WASM component by removing unnecessary custom sections.
> This is especially useful for **Python-based components**, where it can reduce the final binary size by up to **2x**.

---

## Formatting and linting

To install development dependencies and set up pre-commit hooks:

```bash
python3 -m pip install -r requirements-dev.txt
pre-commit install
```

Run Ruff for code style checks:

```bash
ruff .
```

Run Black for formatting:

```bash
black .
```

Or run all pre-commit hooks:

```bash
pre-commit run --all-files
```

---

## Running tests

The test suite mirrors the Docker workflow and requires a WebAssembly runtime.

Set the `WASM_RUNTIME` environment variable to your runtime binary (defaults to `wasmtime`):

```bash
export WASM_RUNTIME=wasmtime
```

Tests for the C example will only run if `clang --version` reports the `wasm32-unknown-wasi` target (see [WASI SDK](#9-wasi-sdk)).

Run tests:

```bash
pytest
```

Run docker-mode tests on an explicit `linux/amd64` image:

```bash
make test-docker-amd64
```

Manual equivalent:

```bash
docker buildx build --platform linux/amd64 --load -t tarawasm:test-amd64 .
TARAWASM_DOCKER_IMAGE=tarawasm:test-amd64 \
TARAWASM_DOCKER_PLATFORM=linux/amd64 \
TARAWASM_RUNTIME_MODE=docker \
WASM_RUNTIME=wasmtime \
PYTHONPATH=. \
python3 -m pytest -k "cli:docker" -vv
```

Run optional upstream integration tests (WIT fixtures pulled from tool repos at pinned commits):

```bash
make test-upstream-amd64
```

Manual equivalent:

```bash
docker buildx build --platform linux/amd64 --load -t tarawasm:test-amd64 .
TARAWASM_DOCKER_IMAGE=tarawasm:test-amd64 \
TARAWASM_DOCKER_PLATFORM=linux/amd64 \
TARAWASM_RUNTIME_MODE=docker \
TARAWASM_UPSTREAM_MODE=docker \
TARAWASM_UPSTREAM_IT=1 \
PYTHONPATH=. \
python3 -m pytest tests/test_upstream_tool_repos.py -vv
```

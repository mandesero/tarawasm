# tarawasm

A simple CLI for WebAssembly component workflow.

## Quickstart

1. **Install everything automatically**

   ```bash
   make install
   ```

   This will:

   * Install system packages (via `apt-get`)
   * Install Go 1.24.3
   * Install Rust (via `rustup`)
   * Install TinyGo 0.37.0
   * Install Python packages from `requirements.txt`
   * Install WASM tools (`wkg`, `wasm-tools`, `cargo-component`)
   * Install Node.js 22.x and JS tools (`jco`, `componentize-js`)

2. **Verify your setup**

   ```bash
   make check
   ```

   Runs both:

   * `make system-check` — checks Go, Rust, TinyGo, Node.js, Python
   * `make sdk-check` — checks installed CLI tools (`jco`, `wkg`, `wasm-tools`, `cargo-component`) and Python packages

3. **Build your project**

   ```bash
   make build
   ```

---

## Manual installation

If you prefer to install dependencies by hand, follow these steps.

### 1. System packages (Debian/Ubuntu)

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential ca-certificates clang cmake curl git gnupg \
  lld llvm patchelf python3 python3-dev python3-pip wget
```

### 2. Go 1.24.3

```bash
GO_VERSION=1.24.3
GO_ARCHIVE="go${GO_VERSION}.linux-amd64.tar.gz"
wget https://go.dev/dl/${GO_ARCHIVE}
sudo rm -rf /usr/local/go
sudo tar -C /usr/local -xzf ${GO_ARCHIVE}
rm ${GO_ARCHIVE}
export PATH="/usr/local/go/bin:$PATH"
```

### 3. Rust

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
. "$HOME/.cargo/env"
```

### 4. TinyGo

```bash
TINYGO_VERSION=0.37.0
TINYGO_DEB="tinygo_${TINYGO_VERSION}_amd64.deb"
wget https://github.com/tinygo-org/tinygo/releases/download/v${TINYGO_VERSION}/${TINYGO_DEB}
sudo dpkg -i ${TINYGO_DEB}
rm ${TINYGO_DEB}
```

### 5. Python packages

Create a `requirements.txt` with:

```text
nuitka>=2.7.2
componentize-py>=0.17.0
click>=8.1.7
```

Then install:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install --no-cache-dir -r requirements.txt
```

### 6. WASM tools (Cargo)

```bash
cargo install --locked --root /usr/local wkg --version 0.10.0
cargo install --locked --root /usr/local wasm-tools
cargo install --locked --root /usr/local cargo-component --version 0.21.1
```

### 7. Node.js 22.x

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### 8. JavaScript tools (npm)

```bash
npm install -g @bytecodealliance/jco@1.9.1 \
               @bytecodealliance/componentize-js@0.7.0
```

---

## Using Docker

You can avoid installing all dependencies locally by using the official Docker image:

```bash
docker pull mandeser0/tarawasm:latest
```

### Convenient alias

Add this alias to your shell configuration (`~/.bashrc` or `~/.zshrc`) to simplify usage:

```bash
alias tarawasm='docker run --rm -v "$PWD":/work -w /work mandeser0/tarawasm'
```

---

## Usage

0. **Provide WIT definitions**
   For example, generate from your WIT descriptions:

   ```bash
   wkg wit build --wit-dir=<..wit-path..>
   ```

   Move the resulting `.wasm` file to your project directory.

1. **Initialize the project**

   ```bash
   tarawasm init --lang <..lang..> --wasm-file <..your-wasm-file..> <..world..>
   ```

   Optionally specify a custom source file:

   ```bash
   tarawasm init --lang <..lang..> --wasm-file <..your-wasm-file..> \
     --src-file <..your-file..> <..world..>
   ```

2. **Generate bindings**

   ```bash
   tarawasm bind
   ```
g
3. **Compile to a WASM component**

   ```bash
   tarawasm build
   ```

## Commands

* `tarawasm init`  — initialize project and save config
* `tarawasm bind`  — generate bindings from WIT
* `tarawasm build` — compile source to WASM component
* `tarawasm clean` — remove build artifacts
* `tarawasm all`   — run clean, bind, build in sequence

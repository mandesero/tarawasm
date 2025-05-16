# tarawasm

A simple CLI for WebAssembly component workflow.

## Build from source

### Dependencies

```bash
sudo apt-get update && sudo apt-get install -y patchelf
pip install nuitka componentize-py

# Install cargo
curl https://sh.rustup.rs -sSf | sh

# WASM tooling
cargo install wkg
cargo install wasm-tools
cargo install wit-bindgen

# Install npm
sudo apt install nodejs
sudo apt install npm

# Install jco: https://github.com/bytecodealliance/jco
npm install @bytecodealliance/jco
npm install @bytecodealliance/componentize-js

# Install Go
wget https://go.dev/dl/go1.24.3.linux-amd64.tar.gz
rm -rf /usr/local/go && tar -C /usr/local -xzf go1.24.3.linux-amd64.tar.gz
export PATH=$PATH:/usr/local/go/bin

# Install TinyGo: https://tinygo.org/getting-started/install/
wget https://github.com/tinygo-org/tinygo/releases/download/v0.37.0/tinygo_0.37.0_amd64.deb
sudo dpkg -i tinygo_0.37.0_amd64.deb
```

### Build

```bash
# Using build script
./build.sh

# Or manually
nuitka --onefile --standalone tarawasm.py -o tarawasm
```


## Usage example

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

3. **Compile to a WASM component**  
   ```bash
   tarawasm build
   ```

## Commands

- `tarawasm init`  — initialize project and save config
- `tarawasm bind`  — generate bindings from WIT
- `tarawasm build` — compile source to WASM component
- `tarawasm clean` — remove build artifacts
- `tarawasm all`   — run clean, bind, build in sequence

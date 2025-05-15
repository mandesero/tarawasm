# tarawasm

A simple CLI for WebAssembly component workflow in Tarantool.

## Build from source

### Dependencies

```bash
sudo apt-get update && sudo apt-get install -y patchelf
pip install nuitka componentize-py

# WASM tooling
cargo install wkg           # for `wkg wit build`
cargo install wasm-tools    # for `wasm-tools`
cargo install wit-bindgen   # for `wit-bindgen-go`
# Install jco: https://github.com/bytecodealliance/jco
# Install TinyGo: https://tinygo.org/getting-started/install/
```

### Build

```bash
# Using build script
./build.sh

# Or manually
nuitka --onefile --standalone tarawasm.py -o tarawasm
chmod +x tarawasm
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

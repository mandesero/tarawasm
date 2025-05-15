# Python Example

This example demonstrates building and running a simple WASM component in Python using Tarawasm.

## Steps

1. **Initialize**
   Extract WIT definitions and save project config:

   ```bash
   tarawasm init --lang python --wasm-file docs:adder@0.1.0.wasm adder
   ```

2. **Generate bindings**

   ```bash
   tarawasm bind
   ```

3. **Write your code**
   Create `main.py` in the project root:

   ```python
   from adder import exports

   class Run(exports.Run):
       def run(self) -> None:
           print("Hello from Python WASM!")
   ```

4. **Build**

   ```bash
   tarawasm build
   ```

   This produces `adder.wasm` in the current directory.

5. **Run**
   Use any WASM runtime, e.g. Wasmtime:

   ```bash
   wasmtime adder.wasm
   # Output:
   Hello from Python WASM!
   ```

# JavaScript Example

This example demonstrates building and running a simple WASM component in JavaScript using Tarawasm.

## Steps

1. **Initialize**
   Extract WIT definitions and save project config:

   ```bash
   tarawasm init --lang js --wasm-file docs:adder@0.1.0.wasm adder
   ```

2. **Generate bindings**

   ```bash
   tarawasm bind
   ```

3. **Write your code**
   Create `main.js` in the project root:

   ```js
   export const run = {
      run: async function() {
         console.info("Hello from JS WASM!")
      }
   }
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
   Hello from JS WASM!
   ```

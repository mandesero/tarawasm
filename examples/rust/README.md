# Rust Example

This example demonstrates building and running a simple WASM component in Rust using Tarawasm.

## Steps

1. **Initialize**
   Extract WIT definitions and save project config:

   ```bash
   tarawasm init --lang rust --wasm-file docs:adder@0.1.0.wasm adder
   ```

2. **Generate bindings**

   ```bash
   tarawasm bind
   ```

3. **Write your code**
   Change `src/lib.rs` in the project root:

   ```rs
   #[allow(warnings)]
   mod bindings;

   use bindings::exports::wasi::cli::run::Guest;

   struct Component;

   impl Guest for Component {
      fn run() -> Result<(),()> {
         println!("Hello from Rust WASM!");
         Ok(())
      }
   }

   bindings::export!(Component with_types_in bindings);
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
   Hello from Rust WASM!
   ```

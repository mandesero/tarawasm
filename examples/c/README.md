# C/C++ Example

This example demonstrates building and running a simple WASM component in C/C++ using Tarawasm.

## Steps

1. **Initialize**
    Extract WIT definitions and save project config:

    ```bash
    tarawasm init --lang c --wasm-file docs:adder@0.1.0.wasm adder
    ```

2. **Generate bindings**

    ```bash
    tarawasm bind
    ```

3. **Write your code**
    Create `component.c` in the project root:

    ```cpp
    #include "adder.h"
    #include <stdio.h>

    bool exports_wasi_cli_run_run(void) {
        printf("Hello from C WASM!\n");
        return true;
    }
    ```

4. **Build**

    ```bash
    tarawasm build
    ```

   This produces `dist/adder.component.wasm`.

5. **Run**
    Use any WASM runtime, e.g. Wasmtime:

    ```bash
    wasmtime dist/adder.component.wasm
    # Output:
    Hello from C WASM!
    ```

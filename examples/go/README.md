# Golang Example

This example demonstrates building and running a simple WASM component in Golang using Tarawasm.

## Steps

1. **Initialize**
    Extract WIT definitions and save project config:

    ```bash
    tarawasm init --lang go --wasm-file docs:adder@0.1.0.wasm adder
    ```

2. **Generate bindings**

    ```bash
    tarawasm bind
    ```

3. **Write your code**
    Create `main.go` in the project root:

    ```go
    package main

    import (
        "fmt"
        "adder-wasm-bindings/internal/wasi/cli/run"
        "go.bytecodealliance.org/cm"
    )


    func init() {
        run.Exports.Run = func() (result cm.BoolResult) {
            fmt.Println("Hello from Go WASM!")
            return cm.BoolResult(true)
        }
    }

    func main() { }
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
    Hello from Go WASM!
    ```

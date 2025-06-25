package main

import (
    "fmt"
    "${world}-wasm-bindings/internal/wasi/cli/run"
    "go.bytecodealliance.org/cm"
)

func init() {
    run.Exports.Run = func() (result cm.BoolResult) {
        fmt.Println("Hello from Go WASM!")
        return
    }
}

func main() {}

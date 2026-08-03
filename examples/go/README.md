# Go example

```console
tarawasm init --lang go --wit ./wit --world adder .
tarawasm bind
tarawasm build
```

The final component is `dist/adder.wasm`. `docs:adder@0.1.0.wasm` is retained
only as a fixture for the separate `tarawasm import` workflow.

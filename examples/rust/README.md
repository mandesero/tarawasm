# Rust example

```console
tarawasm init --lang rust --wit ./wit --world adder .
tarawasm bind
tarawasm build
```

Cargo target data is kept under `.tarawasm/build/rust`; the final component is
`dist/adder.wasm`.

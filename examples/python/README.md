# Python example

This project uses `wit/` as its source contract.

```console
tarawasm init --lang python --wit ./wit --world adder .
tarawasm bind
tarawasm build
```

The final component is `dist/adder.wasm`. To start instead from the checked-in
component fixture, run `tarawasm import --lang python --component
docs:adder@0.1.0.wasm --world adder .` in an empty directory.

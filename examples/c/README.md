# C/C++ example

```console
tarawasm init --lang c --wit ./wit --world adder .
tarawasm bind
tarawasm build
```

Intermediate core modules stay under `.tarawasm/build/c`. The only public
artifact is `dist/adder.wasm`; no `.component.wasm` compatibility copy is made.

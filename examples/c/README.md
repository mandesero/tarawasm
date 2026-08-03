# C/C++ example

Run the checked-in C project from a disposable copy:

```console
cp -R examples/c /tmp/tarawasm-c
cd /tmp/tarawasm-c
tarawasm bind
tarawasm build
```

The WIT contract is in `wit/adder.wit`, the implementation is `main.c`, and
the final component is `dist/adder.wasm`. Intermediate core modules stay under
`.tarawasm/build/c`.

To create a fresh project and regenerate its starter source:

```console
mkdir -p /tmp/tarawasm-c-new
cp -R examples/c/wit /tmp/tarawasm-c-new/wit
cd /tmp/tarawasm-c-new
tarawasm init --lang c --wit ./wit --world adder .
tarawasm bind
tarawasm build
```

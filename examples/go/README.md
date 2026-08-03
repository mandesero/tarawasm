# Go example

This example contains the full versioned WASI imports required by TinyGo's
`wasip2` target. Work on a copy:

```console
cp -R examples/go /tmp/tarawasm-go
cd /tmp/tarawasm-go
tarawasm bind
tarawasm build
```

The WIT contract is in `wit/adder.wit`, the implementation is `main.go`, and
the final component is `dist/adder.wasm`.

To create a fresh Go project from the same contract:

```console
mkdir -p /tmp/tarawasm-go-new
cp -R examples/go/wit /tmp/tarawasm-go-new/wit
cd /tmp/tarawasm-go-new
tarawasm init --lang go --wit ./wit --world adder .
tarawasm bind
tarawasm build
```

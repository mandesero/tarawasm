# Python example

This example is a complete Python component project. Work on a copy so builds
do not add generated files to the repository:

```console
cp -R examples/python /tmp/tarawasm-python
cd /tmp/tarawasm-python
tarawasm bind
tarawasm build
```

The WIT contract is in `wit/adder.wit`, the implementation is `main.py`, and
the final component is `dist/adder.wasm`.

To see source generation from scratch, copy only the contract:

```console
mkdir -p /tmp/tarawasm-python-new
cp -R examples/python/wit /tmp/tarawasm-python-new/wit
cd /tmp/tarawasm-python-new
tarawasm init --lang python --wit ./wit --world adder .
tarawasm bind
tarawasm build
```

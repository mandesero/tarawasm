# JavaScript example

Run the checked-in JavaScript project from a disposable copy:

```console
cp -R examples/js /tmp/tarawasm-js
cd /tmp/tarawasm-js
tarawasm bind
tarawasm build
```

The WIT contract is in `wit/adder.wit`, the implementation is `main.js`, and
the final component is `dist/adder.wasm`.

To create a fresh project and regenerate its starter source:

```console
mkdir -p /tmp/tarawasm-js-new
cp -R examples/js/wit /tmp/tarawasm-js-new/wit
cd /tmp/tarawasm-js-new
tarawasm init --lang js --wit ./wit --world adder .
tarawasm bind
tarawasm build
```

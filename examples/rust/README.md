# Rust example

Run the checked-in Rust project from a disposable copy:

```console
cp -R examples/rust /tmp/tarawasm-rust
cd /tmp/tarawasm-rust
tarawasm bind
tarawasm build
```

The WIT contract is in `wit/world.wit`, the implementation is `src/lib.rs`,
and the final component is `dist/adder.wasm`. Cargo build data stays under
`.tarawasm/build/rust`.

To create a fresh project and regenerate its starter source:

```console
mkdir -p /tmp/tarawasm-rust-new
cp -R examples/rust/wit /tmp/tarawasm-rust-new/wit
cd /tmp/tarawasm-rust-new
tarawasm init --lang rust --wit ./wit --world adder .
tarawasm bind
tarawasm build
```

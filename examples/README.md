# Examples

Each directory is a complete WIT-first project that builds the same `adder`
world with a different language backend.

| Example | Implementation | Notes |
| --- | --- | --- |
| [Python](python) | `main.py` | Built with `componentize-py` |
| [Go](go) | `main.go` | Includes the full WASI imports required by TinyGo |
| [JavaScript](js) | `main.js` | Built with `jco` and `componentize-js` |
| [Rust](rust) | `src/lib.rs` | Built with `cargo-component` |
| [C/C++](c) | `main.c` | Built with the WASI SDK and `wasm-tools` |

## Run a ready project

Copy an example before building so the repository remains unchanged:

```console
cp -R examples/python /tmp/tarawasm-python
cd /tmp/tarawasm-python
tarawasm bind
tarawasm build
```

The validated component is written to `dist/adder.wasm`. Replace `python`
with another directory from the table to try its backend.

If tarawasm is running through the Docker helper from the root README, define
the helper again after changing into the copied directory because it mounts the
current directory.

## Create a project from the example contract

Copy only `wit/` when you want to observe `init` generating the config and
starter source:

```console
mkdir -p /tmp/tarawasm-python-new
cp -R examples/python/wit /tmp/tarawasm-python-new/wit
cd /tmp/tarawasm-python-new
tarawasm init --lang python --wit ./wit --world adder .
tarawasm bind
tarawasm build
```

The README inside each language directory gives the exact command and names
the generated source file. The Go contract intentionally differs because
TinyGo requires the complete versioned `wasi:cli/imports@0.2.x` interface set.

## Import a component

The checked-in `docs:adder@0.1.0.wasm` files are Component Model inputs for the
import workflow. Import one into an empty directory:

```console
mkdir -p /tmp/tarawasm-import
tarawasm import \
    --lang python \
    --component ./examples/python/docs:adder@0.1.0.wasm \
    --world adder \
    /tmp/tarawasm-import
cd /tmp/tarawasm-import
tarawasm bind
tarawasm build
```

# tarawasm

`tarawasm` is a CLI that standardizes a WebAssembly component workflow:

1. initialize project config from an input component
2. generate language bindings from WIT
3. build a runnable guest component

## Contents

- [Supported languages](#supported-languages)
- [How to run tarawasm](#how-to-run-tarawasm)
- [Quickstart](#quickstart)
- [Installation](#installation)
- [Docker usage](#docker-usage)
- [Workflow](#workflow)
- [Command reference](#command-reference)
- [Examples](#examples)
- [Development](#development)
- [Tests](#tests)
- [Troubleshooting](#troubleshooting)

## Supported languages

| Language | `init --lang` | Bind tool | Build tool | Default source | Default output |
| --- | --- | --- | --- | --- | --- |
| Python | `python` | `componentize-py` | `componentize-py` | `main.py` | `<world>.wasm` |
| Go | `go` | `go tool wit-bindgen-go` | `tinygo build` | `main.go` | `<world>.wasm` |
| JavaScript | `js` | `jco guest-types` | `jco componentize` | `main.js` | `<world>.wasm` |
| Rust | `rust` | `cargo component bindings` | `cargo component build` | `src/lib.rs` | `<world>.wasm` |
| C/C++ | `c` | `wit-bindgen c` | `clang` + `wasm-tools component new` | `component.c` | `<world>.component.wasm` |

## How to run tarawasm

In this README, `tarawasm ...` means "run the CLI". You can do it in any of these modes.

### 1) Python module (from source checkout)

```bash
python3 -m tarawasm.cli --help
```

Convenient shell function:

```bash
tarawasm() { python3 -m tarawasm.cli "$@"; }
```

### 2) Standalone binary

```bash
make build
./target/tarawasm --help
```

### 3) Docker image

```bash
docker pull mandeser0/tarawasm:latest
alias tarawasm='docker run --rm -v "$PWD":/work -w /work mandeser0/tarawasm'
```

## Quickstart

Minimal local flow on Debian/Ubuntu (Python guest example):

```bash
# from repository root
make install
make check
tarawasm() { python3 -m tarawasm.cli "$@"; }

mkdir -p demo && cd demo
cp ../examples/python/docs:adder@0.1.0.wasm .

tarawasm init --lang python --wasm-file docs:adder@0.1.0.wasm adder
tarawasm bind
tarawasm build

wasmtime dist/adder.wasm
# Hello from Python WASM!
```

If you do not want local toolchain setup, use [Docker usage](#docker-usage) instead.

## Installation

### Recommended: scripted install

```bash
make install
make check
```

`make install` runs `scripts/install_deps.sh` and installs pinned tool versions.  
`make check` runs both `make system-check` and `make sdk-check`.

### Manual install (Debian/Ubuntu)

If you prefer manual setup, use the same versions as the scripts:

| Category | Required version (or newer) |
| --- | --- |
| Go | `1.26.0` |
| Rust (`rustc`) | `1.93.1` |
| TinyGo | `0.40.1` |
| Node.js | `24.x` |
| Python | `3.10+` |
| Clang (WASI SDK build) | `19.1.5+` with `wasm32-unknown-wasi` target |
| `wkg` | `0.15.0` |
| `wasm-tools` | `1.245.1` |
| `cargo-component` | `0.21.1` |
| `wit-bindgen` (`wit-bindgen-cli`) | `0.53.1` |
| `@bytecodealliance/jco` | `1.17.0` |
| `@bytecodealliance/componentize-js` | `0.19.3` |
| `@bytecodealliance/preview2-shim` | `0.17.8` |
| `componentize-py` | `0.21.0` |
| `nuitka` | `4.0.2` |
| `click` | `8.3.1` |

For exact installation commands, see:

- `scripts/install_deps.sh`
- `scripts/verify-system.sh`
- `scripts/verify-sdk.sh`

## Docker usage

Use Docker when you want reproducible tooling without local installation:

```bash
docker pull mandeser0/tarawasm:latest
alias tarawasm='docker run --rm -v "$PWD":/work -w /work mandeser0/tarawasm'
```

### Installing extra Python deps in Docker mode

When building Python components, install additional packages via:

```bash
tarawasm pip install <package>
tarawasm pip install -r requirements.txt
```

Packages are installed in `./.tarawasm/site-packages` in the mounted project.
That directory is automatically included in Python component builds, persists
across container invocations, and is preserved by `tarawasm clean`.

Manage the same environment without rebuilding the image:

```bash
tarawasm pip list
tarawasm pip show <package>
tarawasm pip check
tarawasm pip uninstall <package>
```

Do not pass pip location options such as `--target`, `--user`, `--prefix`, or
`--root`: tarawasm rejects them so dependencies cannot be silently installed
outside the build import path. Package-provided command-line executables are not
automatically added to `PATH`; this facility is intended for Python imports used
while componentizing. Packages must also be compatible with the Python-to-Wasm
toolchain; installing a package does not make arbitrary native extensions usable
inside a component.

For an advanced custom location, pass the same environment variable to every
install and build container:

```bash
docker run --rm \
  -e TARAWASM_PY_SITE_PACKAGES=/work/.custom-python-site \
  -v "$PWD":/work -w /work mandeser0/tarawasm \
  pip install <package>
docker run --rm \
  -e TARAWASM_PY_SITE_PACKAGES=/work/.custom-python-site \
  -v "$PWD":/work -w /work mandeser0/tarawasm \
  build
```

## Workflow

### 1) Prepare an input component

You need a `.wasm` component file (for example from WIT sources):

```bash
wkg wit build --wit-dir=<path-to-wit>
```

### 2) Initialize project

```bash
tarawasm init --lang <python|go|js|rust|c> --wasm-file <input.wasm> <world>
```

Optional overrides:

```bash
tarawasm init --lang <lang> --wasm-file <input.wasm> --wit-dir ./wit --src-file <source-file> <world>
```

`init` writes `tarawasm.json`, extracts WIT, and generates starter source from templates.
The current config format is strict and unversioned:

```json
{
  "world": "adder",
  "lang": "python",
  "wit_path": "wit",
  "src_file": "main.py",
  "wasm_file": "input.wasm",
  "state_dir": ".tarawasm",
  "dist_dir": "dist"
}
```

Relative paths are resolved from the directory containing `tarawasm.json`.
Commands may be run from that directory or any descendant; tarawasm discovers the
project root by walking upward. Older configs must be updated with `state_dir` and
`dist_dir` before use.

### 3) Generate bindings

```bash
tarawasm bind
```

One-off overrides:

```bash
tarawasm bind --world <world> --wit <wit-path>
```

Language-specific flags must come after `--`:

```bash
tarawasm bind --world <world> -- --tool-specific-flag value
```

Show tool help:

```bash
tarawasm bind --tool-help
```

### 4) Build component

```bash
tarawasm build
```

The default output is `dist/<world>.wasm` (`dist/<world>.component.wasm` for C).
Temporary compiler state owned by tarawasm is stored under `.tarawasm/`.

One-off overrides:

```bash
tarawasm build --world <world> --src <src-file> --wit <wit-path> --out <output.wasm> --clean
```

Language-specific flags must come after `--`:

```bash
tarawasm build --out <output.wasm> -- --tool-specific-flag value
```

Show tool help:

```bash
tarawasm build --tool-help
```

### Language-specific flag examples

```bash
# Python
tarawasm bind -- --help
tarawasm build -- --python-path .

# Go
tarawasm bind -- --versioned
tarawasm build -- -opt=z

# JavaScript
tarawasm bind -- --quiet
tarawasm build -- --world-name adder

# Rust
tarawasm bind -- --quiet
tarawasm build -- --quiet

# C
tarawasm bind -- --rename-world adder
tarawasm build -- -O0
```

## Command reference

| Command | Description |
| --- | --- |
| `tarawasm init` | Initialize project and save config |
| `tarawasm bind` | Generate bindings from WIT |
| `tarawasm build` | Compile source into WASM component |
| `tarawasm clean` | Remove only artifacts recorded in `.tarawasm/artifacts.json` |
| `tarawasm all` | Run `clean` + `bind` + `build` |
| `tarawasm strip` | Remove custom sections from a WASM binary |

`strip` default output:

```bash
tarawasm strip dist/adder.wasm
# writes dist/adder.strip.wasm
```

Custom output:

```bash
tarawasm strip dist/adder.wasm --output dist/adder.min.wasm
```

`clean` never scans for generic names such as `target`, `internal`, or `*.wasm`.
Pre-existing user files and directories are not added to the artifact manifest and
are therefore preserved. The Docker entrypoint runs as the UID/GID that owns the
bind-mounted `/work` directory, so generated files remain host-owned without a
recursive permission change.

## Examples

- [Python example](examples/python/README.md)
- [Go example](examples/go/README.md)
- [JavaScript example](examples/js/README.md)
- [Rust example](examples/rust/README.md)
- [C/C++ example](examples/c/README.md)

## Development

Install development dependencies:

```bash
python3 -m pip install -r requirements-dev.txt
pre-commit install
```

Run linters/formatters:

```bash
ruff .
black .
pre-commit run --all-files
```

Build standalone binary:

```bash
make build
```

## Tests

By default, tests use `wasmtime` as runtime:

```bash
export WASM_RUNTIME=wasmtime
pytest
```

Run docker-mode tests on explicit `linux/amd64` image:

```bash
make test-docker-amd64
```

Manual equivalent:

```bash
docker buildx build --platform linux/amd64 --load -t tarawasm:test-amd64 .
TARAWASM_DOCKER_IMAGE=tarawasm:test-amd64 \
TARAWASM_DOCKER_PLATFORM=linux/amd64 \
TARAWASM_RUNTIME_MODE=docker \
WASM_RUNTIME=wasmtime \
PYTHONPATH=. \
python3 -m pytest -k "cli:docker" -vv
```

Run optional upstream integration tests:

```bash
make test-upstream-amd64
```

Manual equivalent:

```bash
docker buildx build --platform linux/amd64 --load -t tarawasm:test-amd64 .
TARAWASM_DOCKER_IMAGE=tarawasm:test-amd64 \
TARAWASM_DOCKER_PLATFORM=linux/amd64 \
TARAWASM_RUNTIME_MODE=docker \
TARAWASM_UPSTREAM_MODE=docker \
TARAWASM_UPSTREAM_IT=1 \
PYTHONPATH=. \
python3 -m pytest tests/test_upstream_tool_repos.py -vv
```

## Troubleshooting

- `Common option '--...' must be provided before '--'`: pass common CLI options before tool args separator.
- C build fails with target error: ensure `clang --version` reports `wasm32-unknown-wasi` (WASI SDK clang).
- Go `1.26+` with TinyGo: `tarawasm build` auto-sets `GOTOOLCHAIN=go1.25.4+auto` when needed.

# tarawasm

[![Build](https://github.com/mandesero/tarawasm/actions/workflows/build.yaml/badge.svg)](https://github.com/mandesero/tarawasm/actions/workflows/build.yaml)
[![Lint](https://github.com/mandesero/tarawasm/actions/workflows/lint.yaml/badge.svg)](https://github.com/mandesero/tarawasm/actions/workflows/lint.yaml)
[![Docker](https://github.com/mandesero/tarawasm/actions/workflows/docker.yaml/badge.svg)](https://github.com/mandesero/tarawasm/actions/workflows/docker.yaml)

`tarawasm` turns a [WIT](https://component-model.bytecodealliance.org/design/wit.html)
contract into a WebAssembly component. Python, Go, JavaScript, Rust, and C/C++
projects all use the same three commands:

```console
tarawasm init --lang python --wit ./wit --world calculator .
tarawasm bind
tarawasm build
```

The result is a validated Component Model binary at `dist/calculator.wasm`.

## Start in five minutes with Docker

Docker contains every compiler and binding generator. Define this helper in the
directory where you want to create a project:

```bash
tarawasm() {
  docker run --rm -v "$PWD:/work" -w /work mandeser0/tarawasm:latest "$@"
}
```

Create `wit/calculator.wit`:

```wit
package example:calculator@0.1.0;

world calculator {
    export add: func(a: s32, b: s32) -> s32;
}
```

Then initialize and build the component:

```console
tarawasm init --lang python --wit ./wit --world calculator .
tarawasm bind
tarawasm build
```

Tarawasm generates a starter source file from the selected world's exports.
Implement the generated functions, then run `tarawasm build` again.

## Supported languages

| Language | `--lang` | Starter source | Binding and build tools |
| --- | --- | --- | --- |
| Python | `python` | `main.py` | `componentize-py` |
| Go | `go` | `main.go` | `wit-bindgen-go`, TinyGo |
| JavaScript | `js` | `main.js` | `jco`, `componentize-js` |
| Rust | `rust` | `src/lib.rs` | `cargo-component` |
| C/C++ | `c` | `component.c` | `wit-bindgen`, WASI SDK, `wasm-tools` |

TinyGo's `wasip2` target requires the selected Go world to import the complete
versioned `wasi:cli/imports@0.2.x` world. Tarawasm checks the required WASI
interfaces before invoking TinyGo and reports every missing import.

Ready-to-build projects for every language live in [`examples`](examples).
The examples guide shows both how to run a checked-in project and how to create
a fresh project from its WIT contract.

## Initialize from WIT

```console
tarawasm init \
    --lang <python|go|js|rust|c> \
    --wit <file-or-directory> \
    [--world <world>] \
    [project-directory]
```

`--wit` accepts one `.wit` file or a WIT package directory. If the package has
one world, tarawasm selects it automatically. If it has several, tarawasm lists
them and asks for `--world`.

Initialization validates the complete WIT resolution graph before writing any
files. It does not overwrite an existing source file. `--force` may replace
known generated files, but never removes unrelated paths. Preview an operation
without changing the filesystem with `--dry-run`:

```console
tarawasm init --lang rust --wit ./wit --dry-run ./calculator
```

## Import an existing component

Use `import` when the starting point is a Component Model binary rather than a
WIT package:

```console
tarawasm import \
    --lang python \
    --component ./service.wasm \
    --world service \
    ./service-project
```

Core WebAssembly modules are rejected. The input component is left untouched;
its WIT is extracted to `.tarawasm/imported-wit` and passed through the same
world selection and source generation pipeline as `init`. Because the input is
not a generated artifact, `tarawasm clean` never removes it.

## Build workflow

```console
tarawasm bind [--world WORLD] [--wit PATH] [--dry-run] [-- TOOL_ARGS...]
tarawasm build [--world WORLD] [--wit PATH] [--src PATH] [--out PATH] \
    [--clean] [--dry-run] [-- TOOL_ARGS...]
tarawasm all
tarawasm clean
tarawasm strip component.wasm [wasm-tools strip options]
```

`tarawasm all` runs binding generation and the build together. `--tool-help`
shows help for the selected backend tool. Arguments after `--` are passed
directly to that tool as an argument list.

The default output is `dist/<world>.wasm`. A custom `--out`, including a path
outside the project, is published atomically and recorded for safe cleanup. A
failed build keeps the previous successful component intact.

## WIT dependencies

Dependency resolution uses Bytecode Alliance `wkg` and a `wkg.lock` file:

```console
tarawasm deps resolve  # create the lock or fetch its pinned packages
tarawasm deps list
tarawasm deps update   # explicitly update dependency versions
```

Resolved packages remain separate under the WIT package's `deps/` directory.
The project-local cache is `.tarawasm/deps/cache`. Regular `bind` and `build`
commands do not update the lock file. Once the lock and cache are populated,
resolution can reuse the pinned packages offline.

## Configuration and project layout

`tarawasm init` and `tarawasm import` create a strict `tarawasm.json`:

```json
{
  "language": "python",
  "world": "calculator",
  "wit": {
    "path": "wit",
    "package": "example:calculator@0.1.0"
  },
  "source": "main.py",
  "output": "dist/calculator.wasm"
}
```

Paths are relative to the project root containing `tarawasm.json`, so commands
work from any child directory. Unknown fields are rejected with a field-specific
error.

```text
calculator/
├── tarawasm.json
├── wit/                         # source WIT package
├── main.py                      # backend-specific implementation
├── .tarawasm/
│   ├── artifacts.json           # generated artifact manifest
│   ├── build/<language>/        # intermediate build files
│   ├── deps/cache/              # dependency cache
│   └── imported-wit/            # WIT extracted by `import`
└── dist/
    └── calculator.wasm          # final component
```

`tarawasm clean` removes only paths registered in
`.tarawasm/artifacts.json`. It does not scan for `*.wasm`, and it leaves user
directories such as `target/` and `internal/` untouched.

## Install Python packages in Docker

Python component dependencies can persist in the mounted project without
rebuilding the image:

```console
tarawasm pip install -r requirements.txt
tarawasm build
```

Packages are stored in `.tarawasm/site-packages` and reused by
`componentize-py`. Set `TARAWASM_PY_SITE_PACKAGES` to the same custom path for
both install and build if the default is unsuitable.

## Native development and helper scripts

The native installer targets x86-64 Ubuntu and installs the pinned compilers,
SDKs, and Python packages system-wide:

```console
sudo make install
make check
python3 -m tarawasm.cli --help
```

Build a standalone executable with Nuitka:

```console
make build
./target/tarawasm --help
```

Useful repository helpers are exposed as Make targets:

| Command | Purpose |
| --- | --- |
| `make install` | Run `scripts/install_deps.sh` and install the pinned toolchain |
| `make check` | Run system-version and SDK/Python dependency checks |
| `make shellcheck` | Check every tracked shell script |
| `make build` | Create the standalone `target/tarawasm` executable |
| `make test-docker-amd64` | Build the image and run the Docker integration suite |
| `make test-upstream-amd64` | Run integration tests against upstream tool repositories |

For day-to-day use, Docker is the shortest path because it already contains
the exact supported toolchain versions.

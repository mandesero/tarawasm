# tarawasm

[![Build](https://github.com/mandesero/tarawasm/actions/workflows/build.yaml/badge.svg)](https://github.com/mandesero/tarawasm/actions/workflows/build.yaml)
[![Lint](https://github.com/mandesero/tarawasm/actions/workflows/lint.yaml/badge.svg)](https://github.com/mandesero/tarawasm/actions/workflows/lint.yaml)
[![Docker](https://github.com/mandesero/tarawasm/actions/workflows/docker.yaml/badge.svg)](https://github.com/mandesero/tarawasm/actions/workflows/docker.yaml)

`tarawasm` builds WebAssembly components from a
[WIT](https://component-model.bytecodealliance.org/design/wit.html) interface
contract. It creates a starter project, generates language bindings and compiles
a validated `.wasm` component. Supported languages: Python, Go, JavaScript,
Rust, C/C++ and C#.

## Choose how to run

| Option | What runs on your machine | Best when |
| --- | --- | --- |
| pip + local toolchain | Python CLI and tools for your language | You want native builds and editor integration |
| pip + Docker toolchain | Python CLI; language tools run in Docker | You want the CLI locally without installing compilers |
| Full Docker | CLI and all language toolchains in one large image | You want everything in a container, without host Python |

### 1. Install with pip, then choose a toolchain

Requires Python 3.10+:

```sh
pip install tarawasm
tarawasm --help
```

The package installs the CLI; compilers are prepared separately.

For local Python builds:

```sh
tarawasm toolchain setup python --mode local --install
tarawasm toolchain use python --mode local
```

Or use a language-specific Docker image (requires a running Docker daemon):

```sh
tarawasm toolchain setup python --mode docker --install
tarawasm toolchain use python --mode docker
```

Replace `python` with `go`, `js`, `rust`, `c` or `csharp`. Setup installs tools
or downloads images; `use` saves your choice for subsequent projects. Existing
compatible local tools are reused. You can choose a different mode per language.

Automatic local setup supports macOS arm64/x86-64 and glibc Linux x86-64.
macOS needs Xcode Command Line Tools; Rust setup also needs Homebrew.
C# compilation requires Linux amd64, so select Docker for C# on macOS.
Docker images target `linux/amd64`; ARM hosts need Docker's emulation support.
Default language images use `latest-{language}`; choose a release tag explicitly
for pinned builds. See [image selection](docs/usage-reference.md#image-choice).

### 2. Run entirely in Docker

Only Docker is required on the host. The full image includes the CLI and all
supported language toolchains; it is larger than the per-language images.
Define this shell helper in your project directory:

```sh
tarawasm() {
  docker run --rm --platform linux/amd64 \
    -v "$PWD:/work" -w /work mandeser0/tarawasm:latest "$@"
}
```

The commands below now run inside the container. Keep project files and inputs
under the mounted directory. For reproducible builds, replace `latest` with a
published release tag. No `toolchain setup` or `toolchain use` is needed here.

## Create and build a component

Start in an empty project directory. Create `wit/calculator.wit`:

```wit
package example:calculator@0.1.0;

world calculator {
    export add: func(a: s32, b: s32) -> s32;
}
```

Initialize the project and generate bindings:

```sh
tarawasm init --lang python --wit ./wit --world calculator .
tarawasm bind
```

In the generated `main.py`, implement `add`:

```python
import wit_world


class WitWorld(wit_world.WitWorld):
    def add(self, a: int, b: int) -> int:
        return a + b
```

Then build:

```sh
tarawasm build
```

The result is `dist/calculator.wasm`. The same workflow applies to every
language; change `--lang` and edit that language's generated source.
[Ready-to-build examples](examples/README.md) are available for all six languages.

`--wit` accepts a file or package directory. If there is only one world,
`--world` is optional. Initialization validates WIT before writing files and
preserves existing user source.

### Start from an existing component

```sh
tarawasm import --lang python --component ./service.wasm ./service-project
cd service-project
tarawasm bind
# Implement the generated source, then:
tarawasm build
```

`import` extracts the component's WIT and creates a new implementation project.
It leaves the input binary untouched. Core WebAssembly modules are not accepted.

### Everyday commands

| Command | Purpose |
| --- | --- |
| `tarawasm bind` | Generate bindings from the selected WIT world |
| `tarawasm build` | Compile and validate the component |
| `tarawasm all` | Clean generated artifacts, regenerate bindings and build |
| `tarawasm clean` | Remove only artifacts recorded by tarawasm |
| `tarawasm strip dist/calculator.wasm --all` | Write `dist/calculator.strip.wasm` without custom sections |
| `tarawasm doctor --lang python` | Check the selected tools and report problems |

Use `--dry-run` on `init`, `bind` or `build` to preview an operation.
Build options include `--src`, `--out`, `--wit` and `--world`.
Arguments after `--` go to the underlying tool; `--tool-help` shows its help.
A failed build preserves the previous successful output.

## Language notes and packages

| Language | `--lang` | Starter source | Main tools |
| --- | --- | --- | --- |
| Python | `python` | `main.py` | componentize-py |
| Go | `go` | `main.go` | wit-bindgen-go, TinyGo |
| JavaScript | `js` | `main.js` | Jco, ComponentizeJS |
| Rust | `rust` | `src/lib.rs` | cargo-component |
| C/C++ | `c` | `component.c` | wit-bindgen, WASI SDK |
| C# | `csharp` | `Component.csproj`, `src/*Impl.cs` | componentize-dotnet, NativeAOT-LLVM (experimental) |

### Python

With a local toolchain, install component dependencies into the Python
environment used by the selected `componentize-py`:

```sh
python3 -m pip install -r requirements.txt
tarawasm build
```

With **pip CLI + Docker toolchain**, install pure Python dependencies into the
project directory from the host, then build normally:

```sh
pip install --target .tarawasm/site-packages -r requirements.txt
tarawasm build
```

The CLI mounts `.tarawasm/site-packages` into the build container automatically.
Packages installed elsewhere in the host Python are not forwarded. `--target`
changes the install directory, not the package's target platform: host-native
extensions are not usable in Wasm. See the [container installation alternative](docs/usage-reference.md#python-install-requirements)
when installation needs to run inside the selected image.

With **Full Docker**, use the shell function from the installation section:

```sh
tarawasm pip install -r requirements.txt
tarawasm build
```

Dependencies must be compatible with the Wasm build environment.
For sources in a subdirectory, use `tarawasm build --src src/main.py`.

### JavaScript

With a local toolchain or **pip CLI + Docker toolchain**, install JavaScript
dependencies in the project; Docker builds can read its `node_modules`:

```sh
npm install
tarawasm build
```

With **Full Docker**, run `tarawasm npm install` through the shell function.
If installation needs platform-specific tools, run npm in the selected image;
see [package installation by language](docs/usage-reference.md#javascript-install-npm-packages).

Builds bundle local ESM modules and installed npm packages. Only `stdio` is
enabled by default; enable other features explicitly, for example:

```sh
tarawasm build -- --enable http
```

Generated names follow JavaScript conventions: WIT `add-number` becomes
`addNumber`. See [JavaScript features and diagnostics](docs/usage-reference.md#javascript-dependencies-and-features)
for feature selectors and compiler fallback behavior.

ComponentizeJS 0.23.0 cannot build components with same-named resources in
different exported interfaces.

### Go, Rust and C/C++

Go requires the complete versioned `wasi:cli/imports@0.2.x` world for TinyGo's
`wasip2` target; use the [Go example](examples/go/README.md) as a starting point.
Manage Go and Rust dependencies with `go.mod` and `Cargo.toml`. Docker builds
resolve those dependencies inside the selected image; host package caches are
not forwarded. C/C++ dependencies must be supplied as WASI-compatible source,
headers or libraries. See [package installation by language](docs/usage-reference.md#packages-with-pip-cli-and-docker-toolchains).
If you change Go module paths or binding layout, update your source imports too.
C/C++ builds need a WASI SDK compiler and its sysroot.

Rust target changes belong in `Cargo.toml`, with `tarawasm.json` kept in sync;
differing `--world`, `--wit` and `--src` overrides are rejected.

### C#

C# support uses an experimental Linux amd64 toolchain. `source` and `--src`
refer to a `.csproj`; edit the generated implementations in `src/*Impl.cs`.
Add NuGet packages and refresh the lock inside the selected image using the
[package installation recipe](docs/usage-reference.md#c-update-nuget-packages-and-lock-explicitly).
Ordinary builds use locked NuGet dependencies. Async WIT, futures and streams
are not supported. See the [C# example](examples/csharp/README.md) and
[detailed constraints](docs/usage-reference.md#c-components-with-an-experimental-toolchain).

## WIT dependencies and project settings

```sh
tarawasm deps resolve  # Fetch packages using wkg; create/reuse wkg.lock.
tarawasm deps list
tarawasm deps update   # Explicitly update dependency versions.
```

Commit `wkg.lock` at the project root. Normal `bind` and `build` do not update it.
For older projects with `wit/wkg.lock`, move/reconcile that lock at the project
root before resolving dependencies.

`tarawasm.json` stores the language, WIT path/world, source and output paths.
Paths are relative to the project root. `.tarawasm/` holds generated bindings,
intermediates and caches; `dist/` holds the final component. Cleanup follows
`.tarawasm/artifacts.json` and preserves user sources and imported components.

Toolchain choices are saved per user. Use `toolchain use … --project` for a
local project override, or `--execution local|docker` on an operation for a
one-off choice. Tarawasm does not silently switch modes after a failure.
`tarawasm toolchain lock python` records tool versions/image digests in a
committable `tarawasm.toolchain.lock.json`.

For custom tools/images, CI setup, configuration examples and detailed language
behavior, see the [usage reference](docs/usage-reference.md).
For development and repository checks, see [CONTRIBUTING.md](CONTRIBUTING.md).

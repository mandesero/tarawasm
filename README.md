# tarawasm

[![Build](https://github.com/mandesero/tarawasm/actions/workflows/build.yaml/badge.svg)](https://github.com/mandesero/tarawasm/actions/workflows/build.yaml)
[![Lint](https://github.com/mandesero/tarawasm/actions/workflows/lint.yaml/badge.svg)](https://github.com/mandesero/tarawasm/actions/workflows/lint.yaml)
[![Docker](https://github.com/mandesero/tarawasm/actions/workflows/docker.yaml/badge.svg)](https://github.com/mandesero/tarawasm/actions/workflows/docker.yaml)

`tarawasm` turns a [WIT](https://component-model.bytecodealliance.org/design/wit.html)
contract into a WebAssembly component. Python, Go, JavaScript, Rust, C/C++ and C#
projects all use the same three commands:

```console
tarawasm init --lang python --wit ./wit --world calculator .
tarawasm bind
tarawasm build
```

The result is a validated Component Model binary at `dist/calculator.wasm`.

## Select a build environment

The lightweight CLI needs Python 3.10+ and Click. Run it from a checkout:

```sh
python3 -m pip install -r requirements.txt
python3 -m tarawasm.cli --help
tarawasm() { python3 -m tarawasm.cli "$@"; }
```

The examples below use this shell function from the repository directory.
When working elsewhere, set `PYTHONPATH` to the absolute checkout path.

On the first `init` or `import` for a language, tarawasm checks local tools,
versions, and required capabilities. Compatible tools are reported as `found`
and reused. If the toolchain is incomplete and stdin/stdout are terminals,
tarawasm offers local tools or Docker, then offers automatic preparation or a
printed command plan. No partial project is created when preparation fails.
Help and cleanup never start onboarding.

```console
tarawasm toolchain list
tarawasm toolchain status python
tarawasm doctor --lang python
tarawasm doctor --all --json

# Print an installation plan; add --install to execute it.
tarawasm toolchain setup python --mode local
tarawasm toolchain setup python --mode docker --install

# Choose a ready environment for subsequent projects.
tarawasm toolchain use python --mode docker
tarawasm init --lang python --wit ./wit .
tarawasm bind
tarawasm build
```

Automatic local installation supports macOS on Apple Silicon/Intel and glibc
Linux x86-64 (glibc 2.28+): Ubuntu, Debian 12, Fedora 39, CentOS 8, RED OS 7.3.4,
and Astra Linux 1.7, including distributions declaring those families in
`/etc/os-release`. The installer selects `apt-get`, `dnf`, or `yum` for system
prerequisites. Python 3.10+ must already be installed; older distributions may
need a separately prepared Python. Tools are installed beneath the user's data directory, without replacing binaries in
system tool directories. The printed plan includes administrator-managed system
prerequisites. `--install` executes the plan after confirmation; in CI use
`--install --yes`. Compatible existing tools are skipped by default. With `--upgrade`, unlocked
tools older than the catalog recommendation receive managed replacements; newer
compatible tools are retained. Installing a managed
replacement for an outdated/incompatible discovered tool requires `--upgrade`.
Explicit custom binary paths are never overwritten by setup. macOS requires
Python 3.10+ and Xcode Command Line Tools. Preparing the Rust language toolchain
also requires an existing Homebrew installation for build dependencies
(`pkg-config` and `openssl@3`). Go, TinyGo, WASI SDK, and common Wasm tools use
official, checksum-verified macOS releases; TinyGo also installs matching Binaryen
(`wasm-opt`) on both Linux and macOS. JavaScript installation pins the
preview2-shim 0.17.8 dependency used by componentize-js; newer shim releases
remove the default filesystem preopens required by its embedded splicer. Homebrew and system Python are not
installed or replaced by tarawasm. Other platforms can use an existing compatible
local toolchain or Docker. Docker
CLI and a working daemon must already be installed; setup downloads images.

Selection is saved in the user's config directory. `toolchain use --project`
saves a project override in `tarawasm.local.json`, which should not be committed.
`TARAWASM_CONFIG_HOME` and `TARAWASM_DATA_HOME` override these locations for
isolated CI runs. Explicit `--execution local|docker` on an operation overrides
its selection for that invocation. Project settings override user settings.
Tarawasm does not silently switch environments after failures.

```console
tarawasm toolchain use rust --mode docker --image registry.example/team/rust:tested
tarawasm toolchain set rust cargo-component --path /opt/tools/my-cargo-component
tarawasm toolchain lock rust
```

A custom executable must pass its version/capability checks. Multiple local
paths can be configured before the entire toolchain is ready. A Docker image
must provide the tarawasm CLI and its `doctor --json` protocol. Locked local
versions are checked exactly; locked Docker images use registry digests.
`tarawasm.toolchain.lock.json` is portable and can be committed. Locks constrain
versions across execution modes. An explicit image differing from a lock is
rejected; edit/remove the lock before intentionally changing the pinned image.
The managed installer can supply its catalog versions; other locked versions
must be provided manually or through a matching Docker image.

Without a terminal, missing/ambiguous setup choices return an error with a
command to run. `--non-interactive` disables questions even with a terminal.
Inside a tarawasm image, tools execute directly without nested Docker.

## Prepare all toolchains in CI

```console
tarawasm toolchain setup --all --mode local --install --yes
tarawasm toolchain setup --all --mode docker --install --yes
tarawasm doctor --all --json
```

Setup prepares tools/images and checks every requested language. It does not
change active selections; choose them with `toolchain use`. `--all --image
registry.example/team/all:tested` prepares and checks one shared full image.
To reuse a saved custom image or project lock, omit `--image`; setup preserves
the effective profile. `doctor` returns a nonzero status for missing, outdated,
incompatible, unknown, or unavailable requirements. Status/list never pull an
image, and images without a local copy are reported as `not downloaded`.

## Language-specific Docker images

`Dockerfile` has targets `base`, `python`, `go`, `js`, `rust`, `c`, `csharp`, and `all`.
The default `all` target preserves the previous full-image workflow. Language
images copy only their required tools from the shared build stage. Build and
use a local image before the toolchain image family has been published:

```console
docker buildx build --platform linux/amd64 --target python --load -t tarawasm:python .
tarawasm toolchain use python --mode docker --image tarawasm:python
```

The default release references are maintained in
`tarawasm/toolchains/catalog.json`; publication is a separate release step.
All current language images target `linux/amd64`. On an ARM host Docker must
support running that platform. Existing installed tools may be newer when they
satisfy supported ranges; version ranges also include upper bounds where
required, such as Go/TinyGo compatibility. A C compiler must be a WASI SDK
compiler with its sysroot, and Rust needs the `wasm32-wasip1` target.

Docker execution preserves host paths and file ownership. Only the current
working directory, project, explicit external inputs, and output locations are
mounted. Run from a project directory rather than a broad parent directory.
Registry images run as the host UID without a Docker socket or privileged mode.
JavaScript execution also mounts an operation-local, readonly account description
so Wizer can resolve that UID; the host's account database is never mounted.
Project Python packages installed through the image entrypoint remain supported:

```console
docker run --rm -v "$PWD:/work" -w /work tarawasm:python pip install -r requirements.txt
```

## C# components with an experimental toolchain

C# uses [componentize-dotnet](https://github.com/bytecodealliance/componentize-dotnet)
and NativeAOT-LLVM. The pinned configuration is .NET SDK **10.0.402**,
`BytecodeAlliance.Componentize.DotNet.Wasm.SDK` **0.8.0-preview00011**,
NativeAOT-LLVM **10.0.0-rc.1.26306.1**, its C# `wit-bindgen` **0.58.0**,
and a separate WASI SDK **29.0**. These upstream dependencies are experimental.
The C backend continues to use its own WASI SDK version from the catalog.

Compilation requires **Linux amd64**. This compiler does not support local
macOS arm64 or amd64 builds. Running a finished component on macOS is separate
from compiling it. Choose Docker explicitly on macOS; failures never change
execution mode or architecture automatically:

```sh
docker buildx build --platform linux/amd64 --target csharp --load -t tarawasm:csharp .
tarawasm toolchain use csharp --mode docker --image tarawasm:csharp
tarawasm init --lang csharp --wit ./wit --world calculator .
tarawasm bind
tarawasm build
```

On Linux amd64, `toolchain setup csharp --mode local --install --yes` installs
the pinned SDK, NuGet packages and WASI SDK under the managed data directory.
It compiles and validates a probe component. `doctor --lang csharp --json`
checks the SDK version, binding generator, WASI SDK version and a cached
capability receipt tied to tool contents and the probe component. Presence of
`dotnet` alone is insufficient. `toolchain list/status/setup/use/set/lock` and
`--all` include C#. Consequently, `doctor --all` and local `setup --all` on
macOS report the C# platform limitation; select Docker for C# separately.

For C#, `source` and `build --src` identify a **`.csproj`**, not a `.cs` file or
directory. The generated project compiles user files from its sibling
`src/**/*.cs`. An alternate project needs the same tarawasm project settings,
its own `global.json`, `nuget.config`, lock and sources. Docker mounts an
external C# project directory read-only so these sibling inputs are visible;
intermediates stay under the tarawasm project's `.tarawasm/build/csharp/`.

`init` generates implementation files using the pinned generator's
`--generate-stub`, including exact versioned namespaces, hyphenated names,
keyword escaping and resource signatures. Replace the marked
`NotImplementedException` bodies. Repeated `bind` and `build` never regenerate
these user implementations. Bindings, NuGet download cache and compiler
intermediates are separate generated artifacts. `clean` preserves the project,
sources, WIT, imported components, SDK settings and NuGet lock.

Both `bind` and `build` invoke the same pinned C# generator with UTF-8 strings,
NativeAOT and `--with-wit-results`; MSBuild's automatic WIT generation is
disabled to avoid duplicate bindings and its upstream path-quoting problem.
`bind -- --internal` changes binding visibility. `build --` accepts MSBuild
`-p:Name=Value`, verbosity options, `--no-incremental` and
`--disable-build-servers`; output, ABI and lock settings remain managed.
Builds disable persistent compiler servers and use one MSBuild worker so each
operation owns its compiler state, including in unprivileged Docker containers.
Use `--tool-help` to inspect the underlying generator or `dotnet build` help.
`--world`, `--wit`, `--src`, `--out` and `--dry-run` follow the shared CLI rules.
For external Docker inputs, use canonical absolute paths or paths relative to
the project. Host path aliases such as macOS `/var` versus `/private/var` are
not reproduced inside the container.

Ordinary bind/build always restore with the committed lock and fail on a
dependency mismatch. To change dependencies intentionally, edit the project
and explicitly run `dotnet restore --use-lock-file --force-evaluate
-p:RestoreLockedMode=false --configfile nuget.config`, then review and commit
the new lock. NuGet feeds and .NET settings are scoped to the project or
managed environment; global user configuration is not changed. Docker images
contain a read-only package fallback cache and use writable caches owned by
the invoking UID.

Direct world functions, exported interfaces, versioned external WIT packages
and synchronous resources use ordinary Component Model imports/exports.
Imported resources implement `IDisposable`; use `using` to release them.
Async WIT functions, `future`, `stream`, `error-context` and fixed-length lists
are rejected with a diagnostic. C# support does not imply support for arbitrary
.NET applications or the entire standard library. See the
[C# example](examples/csharp/README.md) for build and execution instructions.

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
| C# | `csharp` | `Component.csproj`, `src/*Impl.cs` | .NET, componentize-dotnet, NativeAOT-LLVM; experimental toolchain, Linux amd64 |

TinyGo's `wasip2` target requires the selected Go world to import the complete
versioned `wasi:cli/imports@0.2.x` world. Tarawasm checks the required WASI
interfaces before invoking TinyGo and reports every missing import.

The recommended Go toolchain is Go 1.27.2, TinyGo 0.43.0 and Binaryen 133.
`toolchain setup go --mode local --install --yes` installs verified release
archives on Linux amd64 and macOS arm64/amd64. Use the same command with
`--upgrade` to update an unlocked managed 0.42 installation. TinyGo 0.42 remains
supported with Binaryen 116. Compiler and optimizer archives are verified by
version/platform SHA256 before the complete TinyGo release is replaced; a failed
download or checksum preserves the previous compiler/optimizer release.

Tarawasm supplies the managed tool paths to each CLI operation. For Go it pins
`WASMOPT` to the optimizer selected from PATH or the compiler's directory;
an explicit `WASMOPT` takes priority. `doctor --lang go` checks that optimizer's
version against the selected TinyGo release and includes its path/version in
the report. A new CLI process finds installed managed tools without shell PATH
changes. Source-built Docker Go/full images use the same catalog and verified
Linux archives, including an external Binaryen installation.

Ordinary builds retain TinyGo's default asyncify scheduler. To select the
explicit unwind mode, pass the flags yourself:

```sh
tarawasm build -- -scheduler=none -panic-unwind=explicit
```

Tarawasm does not add these flags automatically. Runtime regression tests exercise
goroutine/channel scheduling in the default mode and nested defer/panic/recover
behavior in the explicit mode, in addition to component stripping and validation.

Go scaffolds follow the catalog-pinned `wit-bindgen-go` representation: WIT
package/world/interface paths keep their hyphens, named types use the binding
package alias, homogeneous tuples use arrays, and heterogeneous tuples use
`cm.Tuple` or `cm.Tuple3` through `cm.Tuple16`. Anonymous longer tuples and
results with distinct payload types use generic TODO helpers that infer the
exact signature from the bindings, including their private layout/storage types.
The `cm` import is emitted only when the scaffold uses it.

Go module paths remain user-owned. When changing `go.mod` or using bindgen
layout flags such as `bind -- --versioned`, update the implementation's imports
to match (for example, `example.org/team/project/internal/docs/my-pkg/v0.1.0/my-world`).
`bind` passes these flags through and does not rewrite source files.

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

## JavaScript dependencies and features

JavaScript builds enable Jco bundling by default. ESM imports from local files
and installed npm packages are bundled; WIT imports remain external. The `js`
Docker target includes the complete Node distribution with npm and npx:

```console
docker run --rm -v "$PWD:/work" -w /work tarawasm:js-test-amd64 npm install ./sdk.tgz
tarawasm build
tarawasm build -- --enable http
```

The default feature set contains only `stdio`. User selectors `--enable`,
`--disable` (or `-d`) accept multiple feature names: `clocks`, `http`, `random`,
`stdio`, `fetch-event`, and `all`. Selectors apply in command-line order, with
the last selection for each feature taking priority. For example,
`build -- --disable all --enable http` enables only HTTP. Other Jco arguments
remain available after `--`.

Generated JavaScript uses camelCase for WIT functions, interfaces, parameters,
and resource methods, and PascalCase for resource classes: `add-number` becomes
`addNumber`, and `number-box.get-number` becomes `NumberBox.getNumber`.
Existing user source files remain untouched by initialization.

To diagnose compiler selection, inspect `tarawasm doctor --lang js --json`
for the dependency resolved by the selected Jco, and inspect build stderr.
[Jco can fall back to ComponentizeJS 0.19.3](https://bytecodealliance.github.io/jco/troubleshooting/common-issues.html#componentize-js-0193-fallback)
when WIT requests older WASI packages, even with ComponentizeJS 0.23.0 installed.
The warning reports that fallback. Before stripping producers metadata, check
the compiler recorded in the actual component:

```console
wasm-tools metadata show dist/component.wasm --json
```

Update the project's WASI WIT dependencies to compatible versions (0.2.10 or
newer) explicitly when appropriate; ordinary builds do not update WIT locks.

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

Python sources may live in a subdirectory, for example `"source": "src/main.py"`
or `tarawasm build --src src/main.py`. Builds search the source directory first,
then the project root for bindings and dependencies. Additional import paths
can be passed with `tarawasm build -- --python-path extra`.

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

The native installer supports macOS arm64/x86-64 and glibc Linux x86-64 from the
Debian/Ubuntu/Astra and Fedora/CentOS/RED OS families, and prepares pinned compilers,
SDKs, and Python packages in managed user directories:

```console
make install
make check
python3 -m tarawasm.cli --help
```

Useful repository helpers are exposed as Make targets:

| Command | Purpose |
| --- | --- |
| `make install` | Run `scripts/install_deps.sh` and install the pinned toolchain |
| `make check` | Run system-version and SDK/Python dependency checks |
| `make shellcheck` | Check every tracked shell script |
| `make test-docker-amd64` | Build the image and run the Docker integration suite |
| `make test-upstream-amd64` | Run integration tests against upstream tool repositories |

For day-to-day use, Docker is the shortest path because it already contains
the exact supported toolchain versions.

To verify real installed local toolchains, enable the integration suite:

```sh
TARAWASM_LOCAL_TOOLCHAIN_IT=1 PYTHONPATH=. python3 -m pytest tests/test_toolchain_local.py -vv
```

Each language selects a saved local profile, imports a component, generates
bindings, builds and strips an external output, and checks cleanup ownership.

Wkg 0.16.1 stores `wkg.lock` at the project root. If a project has an older `wit/wkg.lock`, explicitly move it to the project root (reconcile both files if both exist) before `deps resolve` or `deps update`. Tarawasm refuses to ignore legacy pins. `deps update` regenerates the lock through `wkg fetch`, because the upstream update command is unfinished; a failed fetch restores the previous lock.

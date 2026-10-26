# Usage reference

[Quick start](../README.md) · [Examples](../examples/README.md) ·
[Contributing](../CONTRIBUTING.md)

## Contents

- [Toolchain setup](#toolchain-setup)
- [Selection, custom tools and locks](#selection-custom-tools-and-locks)
- [CI setup](#ci-setup)
- [Docker images](#docker-images)
- [Python packages and paths](#python-packages-and-paths)
- [JavaScript dependencies and features](#javascript-dependencies-and-features)
- [Go toolchain and bindings](#go-toolchain-and-bindings)
- [C# components with an experimental toolchain](#c-components-with-an-experimental-toolchain)
- [WIT dependencies](#wit-dependencies)
- [Configuration and project layout](#configuration-and-project-layout)

## Toolchain setup

### Supported local platforms

| Platform | Requirements |
| --- | --- |
| macOS arm64/x86-64 | Python 3.10+, Xcode Command Line Tools; Homebrew for Rust build dependencies |
| Linux x86-64, glibc 2.28+ | Python 3.10+; apt-get, dnf or yum for system prerequisites |
| C# compilation | Linux amd64; use Docker on macOS |

Supported Linux families include Ubuntu, Debian 12, Fedora 39, CentOS 8,
RED OS 7.3.4 and Astra Linux 1.7. Other platforms can use compatible existing
tools or Docker. Docker requires an installed CLI and running daemon.

### Install or upgrade

```sh
tarawasm toolchain setup python --mode local                 # Show the plan.
tarawasm toolchain setup python --mode local --install       # Confirm and install.
tarawasm toolchain setup python --mode local --install --yes # Install without prompts.
tarawasm toolchain setup python --mode local --install --upgrade
```

| Behavior | Rule |
| --- | --- |
| Install location | Managed user data directory; system tool binaries are not replaced |
| Existing compatible tools | Reused by default |
| Older/incompatible tools | Managed replacement requires `--upgrade` |
| Newer compatible tools | Retained, including with `--upgrade` |
| Custom executable paths | Never overwritten by setup |
| System prerequisites | Included in the plan; may require administrator privileges |

Go, TinyGo, Binaryen, WASI SDK and common Wasm releases are checksum-verified.
Homebrew and system Python must already exist; tarawasm does not install them.

## Selection, custom tools and locks

### Select an environment

```sh
tarawasm toolchain use python --mode local
tarawasm toolchain use python --mode docker --project
tarawasm build --execution local
```

Selection priority is: operation `--execution`, project settings, user settings.
A failed operation never silently switches environments.

| File or variable | Purpose |
| --- | --- |
| `tarawasm.local.json` | Project override; do not commit |
| `TARAWASM_CONFIG_HOME` | Override the user configuration directory |
| `TARAWASM_DATA_HOME` | Override managed tool/cache storage |
| `tarawasm.toolchain.lock.json` | Portable toolchain lock; can be committed |

### Custom tools and images

These are separate examples; select local mode before setting a local tool path:

```sh
tarawasm toolchain use rust --mode local
tarawasm toolchain set rust cargo-component --path /opt/tools/my-cargo-component
```

```sh
tarawasm toolchain use rust --mode docker --image registry.example/team/rust:tested
```

Custom executables must pass version/capability checks. Custom Docker images
must provide tarawasm and its `doctor --json` protocol.

### Lock a ready toolchain

```sh
tarawasm toolchain lock rust
```

Local versions are checked exactly; Docker images are pinned by registry digest.
Locks constrain both execution modes. To intentionally change a pinned image,
edit/remove the lock first. Setup can install catalog versions; other locked
versions need a matching manually prepared toolchain or image.

## CI setup

Choose one preparation mode:

```sh
tarawasm toolchain setup --all --mode local --install --yes
```

```sh
tarawasm toolchain setup --all --mode docker --install --yes
```

Then select the mode for each language used by the job and check readiness:

```sh
tarawasm toolchain use python --mode docker
tarawasm doctor --lang python --json
```

| Option/command | Behavior |
| --- | --- |
| `setup --all` | Prepares and checks every language; does not change selections |
| `setup --all --image IMAGE` | Prepares one shared full image |
| Omit `--image` | Preserve saved custom images and project locks |
| `doctor --all --json` | Check every selected toolchain; local C# is unavailable on macOS |
| `toolchain list` / `toolchain status python` | Inspect without pulling images |
| `--non-interactive` | Disable setup questions; missing choices produce an actionable error |

`doctor` exits nonzero for missing, outdated, incompatible, unknown or unavailable
requirements. An image absent locally is reported as `not downloaded`.

## Docker images

### Image choice

| Image | Contents |
| --- | --- |
| `mandeser0/tarawasm:latest` or a full-image release tag | CLI and all language tools |
| `mandeser0/tarawasm:latest-{language}` | CLI and tools for `python`, `go`, `js`, `rust`, `c` or `csharp` |

Default language image references are defined in
[`catalog.json`](../tarawasm/toolchains/catalog.json). Pushes to `master` publish
`latest-{language}` after verification. Git tags publish `{git-tag}-{language}`
without updating `latest` or older release tags. Select a release explicitly
with `toolchain use python --mode docker --image mandeser0/tarawasm:v0.4.0-python`
(using an available release tag). Saved selections and digest locks are preserved. All images target `linux/amd64`; ARM hosts require
Docker's emulation support.

For package commands and direct tools in Docker, this guide assumes the
[`tarawasm` shell helper from the README](../README.md#2-run-entirely-in-docker).
For example, `tarawasm npm install` runs npm inside the full image.

### Paths and ownership

| Execution mode | Mounted inputs |
| --- | --- |
| Full-Docker helper | Current directory at `/work`; keep inputs beneath it |
| pip CLI + Docker toolchain | Project, working directory and explicit external input/output paths; host paths preserved |

Run from the project directory. Generated files retain host ownership. Docker
toolchains run without privileged mode or a Docker socket; tools inside images
execute directly, without nested Docker. JavaScript builds use an operation-local
account description for Wizer rather than mounting the host account database.

### Build a custom language image

From a repository checkout, build the needed target and select it with the
pip-installed CLI:

```sh
docker buildx build --platform linux/amd64 --target python --load -t tarawasm:python .
tarawasm toolchain use python --mode docker --image tarawasm:python
```

Dockerfile targets: `base`, `python`, `go`, `js`, `rust`, `c`, `csharp`, `all`.
The default `all` target includes every language toolchain.

## Python packages and paths

| Mode | Install component dependencies |
| --- | --- |
| Local | `python3 -m pip install -r requirements.txt` in the build Python environment |
| Docker helper | `tarawasm pip install -r requirements.txt` |

Docker packages persist under `.tarawasm/site-packages`. To change that location,
pass the same `TARAWASM_PY_SITE_PACKAGES` into every install and build container.
The pip-installed CLI has no `pip` subcommand; Docker package commands use the
shell helper.

For source files outside the project root:

```sh
tarawasm build --src src/main.py
tarawasm build -- --python-path extra
```

Builds search the source directory first, then the project root for bindings and
dependencies. Packages must be compatible with the Wasm build environment.

## JavaScript dependencies and features

### Packages and bundling

Install with local npm, or use the Docker helper:

```sh
tarawasm npm install ./sdk.tgz
tarawasm build
```

Jco bundles local ESM files and installed npm packages by default. WIT imports
remain external. Docker JS/full images include Node, npm and npx.

### Feature selection

```sh
tarawasm build -- --enable http
tarawasm build -- --disable all --enable http
```

| Setting | Values/behavior |
| --- | --- |
| Default | `stdio` only |
| Available features | `clocks`, `http`, `random`, `stdio`, `fetch-event`, `all` |
| Selectors | `--enable`, `--disable` (or `-d`); accept multiple names |
| Repeated selectors | Applied in order; last selection per feature wins |

Other Jco options pass through after `--`.

### Generated names

| WIT | JavaScript |
| --- | --- |
| `add-number` | `addNumber` |
| `number-box.get-number` | `NumberBox.getNumber` |

Functions, interfaces, parameters and resource methods use camelCase; resource
classes use PascalCase. Initialization preserves existing user source.

### Compiler diagnostics

```sh
tarawasm doctor --lang js --json
```

Inspect build stderr and the component's producer metadata. With the Docker helper:

```sh
tarawasm wasm-tools metadata show dist/component.wasm --json
```

[Jco may fall back to ComponentizeJS 0.19.3](https://bytecodealliance.github.io/jco/troubleshooting/common-issues.html#componentize-js-0193-fallback)
for older WASI packages even when ComponentizeJS 0.23.0 is installed. The build
warns when this happens. Update WIT dependencies explicitly to compatible WASI
versions (0.2.10+) when appropriate; ordinary builds preserve locks.

The installer pins preview2-shim 0.17.8 because newer releases remove filesystem
preopens needed by ComponentizeJS's embedded splicer.

## Go toolchain and bindings

### Versions and prerequisites

| Tool | Recommended | Also supported |
| --- | --- | --- |
| Go | 1.27.2 | Catalog-compatible versions |
| TinyGo | 0.43.0 | 0.42 with Binaryen 116 |
| Binaryen (`wasm-opt`) | 133 for TinyGo 0.43 | Must match TinyGo compatibility rules |

The selected world must import the complete versioned `wasi:cli/imports@0.2.x`
world for TinyGo's `wasip2` target. Tarawasm reports missing interfaces before
compilation. Start with the [Go example](../examples/go/README.md).

```sh
tarawasm toolchain setup go --mode local --install --yes
tarawasm doctor --lang go
```

Add `--upgrade` to replace an older managed toolchain. Failed downloads/checksums
preserve the previous compiler and optimizer. Managed paths are supplied to CLI
operations without shell PATH changes; an explicit `WASMOPT` takes priority.

### Scheduler and binding layout

Normal builds retain TinyGo's default asyncify scheduler. For explicit unwind:

```sh
tarawasm build -- -scheduler=none -panic-unwind=explicit
```

| Binding detail | Representation |
| --- | --- |
| Package/world/interface paths | Preserve WIT hyphens |
| Named types | Use the binding package alias |
| Homogeneous tuples | Arrays |
| Heterogeneous tuples | `cm.Tuple`, `cm.Tuple3` … `cm.Tuple16` |
| Longer anonymous tuples or distinct result payloads | TODO helpers infer the binding signature |

Go module paths remain user-owned. After changing `go.mod` or using
`bind -- --versioned`, update implementation imports to match. `bind` forwards
options without rewriting user source.

## C# components with an experimental toolchain

### Platform and pinned versions

Compilation requires **Linux amd64**. On macOS, choose a Docker toolchain or
use the full-Docker helper. An installed `dotnet` alone does not establish
component compilation support.

| Dependency | Pinned version |
| --- | --- |
| .NET SDK | 10.0.402 |
| Componentize.DotNet.Wasm.SDK | 0.8.0-preview00011 |
| NativeAOT-LLVM | 10.0.0-rc.1.26306.1 |
| C# wit-bindgen | 0.58.0 |
| WASI SDK for C# | 29.0; independent of the C backend SDK |

[componentize-dotnet](https://github.com/bytecodealliance/componentize-dotnet)
and NativeAOT-LLVM are experimental. See the [C# example](../examples/csharp/README.md).

### Project and generated files

| Input/artifact | Rule |
| --- | --- |
| `source` / `build --src` | A `.csproj`, not a `.cs` file or directory |
| User implementation | Sibling `src/**/*.cs`; replace generated `NotImplementedException` bodies |
| Alternate project | Needs its own sources, `global.json`, `nuget.config` and NuGet lock |
| `bind` / `build` | Do not regenerate user implementations |
| Intermediates | `.tarawasm/build/csharp/` |
| `clean` | Preserves project, sources, WIT, imported components, SDK settings and lock |

Docker toolchains mount an external project directory read-only, including its
sibling inputs. Use canonical absolute paths or project-relative paths; host
aliases such as macOS `/var` versus `/private/var` are not recreated.

### Options and diagnostics

```sh
tarawasm doctor --lang csharp --json
tarawasm bind -- --internal
tarawasm build -- -p:Name=Value
tarawasm build --tool-help
```

`doctor` checks versions, tools and a cached compile-capability probe. Both
binding/build paths use UTF-8 strings, NativeAOT and `--with-wit-results`;
automatic MSBuild WIT generation is disabled to avoid duplicate bindings.

Build passthrough also accepts verbosity options, `--no-incremental` and
`--disable-build-servers`. Output, ABI and lock settings remain managed.
Builds use one worker and disable persistent compiler servers.

### Change NuGet dependencies

Ordinary bind/build restores with the existing lock and fails on a mismatch.
To intentionally update dependencies, edit the project and run this in its
prepared .NET environment, then review and commit the new lock:

```sh
dotnet restore --use-lock-file --force-evaluate \
  -p:RestoreLockedMode=false --configfile nuget.config
```

With the full-Docker helper, prefix that command with `tarawasm`.
NuGet feeds and .NET settings are scoped to the project or managed environment.
Docker uses a read-only package fallback cache and UID-owned writable caches.

### WIT support

| Supported | Not supported |
| --- | --- |
| Direct world functions, interfaces, versioned packages, synchronous resources | Async functions, `future`, `stream`, `error-context`, fixed-length lists |

Imported resources implement `IDisposable`; release them with `using`. This
backend does not support arbitrary .NET applications or the entire standard library.

## WIT dependencies

| Command | Purpose |
| --- | --- |
| `tarawasm deps resolve` | Create a lock or fetch its pinned packages |
| `tarawasm deps list` | List dependencies |
| `tarawasm deps update` | Explicitly update versions |

| Path | Contents |
| --- | --- |
| `wkg.lock` at project root | Dependency pins; commit this file |
| WIT package `deps/` | Resolved WIT packages |
| `.tarawasm/deps/cache` | Project-local package cache |

Normal `bind` and `build` preserve locks. Populated locks/caches allow pinned
packages to be reused offline. Move/reconcile legacy `wit/wkg.lock` at the
project root before resolving or updating. With wkg 0.16.1, updates use
`wkg fetch`; a failed fetch restores the previous lock.

## Configuration and project layout

`init` and `import` create `tarawasm.json`:

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

Paths are relative to the project root, so commands work from child directories.
Unknown fields are rejected with a field-specific error.

```text
calculator/
├── tarawasm.json
├── wit/                         # WIT contract
├── main.py                      # user implementation
├── .tarawasm/
│   ├── artifacts.json           # generated artifact manifest
│   ├── build/<language>/        # intermediate files
│   ├── deps/cache/              # WIT package cache
│   └── imported-wit/            # extracted component WIT
└── dist/
    └── calculator.wasm          # validated component
```

`clean` removes only manifest-registered generated artifacts. It does not scan
for `*.wasm` or remove user-owned `target/` or `internal/` directories.

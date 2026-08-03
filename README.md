# tarawasm

`tarawasm` builds WebAssembly components from a WIT contract with the same
workflow for Python, Go, JavaScript, Rust, and C/C++.

> This is a breaking WIT-first release. Projects created by older releases are
> not migrated. Reinitialize them with `tarawasm init` from their WIT package or
> with `tarawasm import` from an existing component.

## Quick start

Create a WIT package:

```wit
package example:calculator@0.1.0;

world calculator {
    export add: func(a: s32, b: s32) -> s32;
}
```

Initialize, generate bindings, and build:

```console
tarawasm init --lang python --wit ./wit --world calculator .
tarawasm bind
tarawasm build
```

The final, validated Component Model binary is always written to
`dist/calculator.wasm`. Replace `python` with `go`, `js`, `rust`, or `c` to use
another backend:

```console
tarawasm init --lang go     --wit ./wit --world calculator ./go-component
tarawasm init --lang js     --wit ./wit --world calculator ./js-component
tarawasm init --lang rust   --wit ./wit --world calculator ./rust-component
tarawasm init --lang c      --wit ./wit --world calculator ./c-component
```

TinyGo's `wasip2` target requires the selected Go world to include the complete
versioned `wasi:cli/imports@0.2.x` imports world. Tarawasm validates all required
WASI interfaces before invoking TinyGo and lists every missing import instead
of creating a hidden wrapper world.

`--wit` accepts either one `.wit` file or a WIT package directory. If the
package defines exactly one world, `--world` is optional. With multiple worlds,
tarawasm lists them and requires an explicit choice.

Initialization validates the complete WIT resolution graph before writing. It
does not overwrite an existing source file. `--force` is limited to known
generated project files and never removes unrelated paths. To inspect an init
without changing the filesystem:

```console
tarawasm init --lang python --wit ./wit --dry-run ./component
```

## Import an existing component

Import is a separate first-class workflow:

```console
tarawasm import \
    --lang python \
    --component ./service.wasm \
    --world service \
    ./service-project
```

The input must be a WebAssembly Component Model binary; core modules are
rejected. WIT is extracted into `.tarawasm/imported-wit` and then handled by the
same parser, world selection, and source generator as WIT-first init. The input
component is neither modified nor registered as a generated artifact, so
`tarawasm clean` never removes it.

There is no `init --wasm-file` compatibility option.

## Configuration

The config has one strict current form:

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

There is no schema/version field, compatibility layer, or automatic migration.
Legacy and unknown fields are rejected. Paths are resolved relative to the
project root containing `tarawasm.json`; commands may be run from any child
directory.

## Commands and overrides

```console
tarawasm bind [--world WORLD] [--wit PATH] [--dry-run] [-- TOOL_ARGS...]
tarawasm build [--world WORLD] [--wit PATH] [--src PATH] [--out PATH] \
    [--clean] [--dry-run] [-- TOOL_ARGS...]
tarawasm all
tarawasm clean
tarawasm strip component.wasm [wasm-tools strip options]
```

`--tool-help` displays the selected backend tool's help. Arguments following
`--` are passed as an argv list directly to that tool. A custom `--out`,
including a path outside the project, is published atomically and recorded for
safe cleanup. A failed build leaves the previous successful output untouched.

## WIT dependencies

Dependency resolution uses Bytecode Alliance `wkg` and its `wkg.lock` file:

```console
tarawasm deps resolve  # create the initial lock or fetch locked packages
tarawasm deps list
tarawasm deps update   # explicitly change locked versions
```

Resolved packages remain separate under the WIT package's `deps/` directory;
they are not flattened into the main WIT file. The project-local download cache
is `.tarawasm/deps/cache`. Normal `bind` and `build` never update the lock file.
With the lock and cache populated, `deps resolve` can reuse the pinned packages
without changing versions.

## Project layout

```text
component/
├── tarawasm.json
├── wit/                         # source WIT package
├── main.py                      # backend-specific starter source
├── .tarawasm/
│   ├── artifacts.json           # generated artifact manifest
│   ├── build/<language>/         # intermediate build files
│   ├── deps/cache/               # dependency cache
│   └── imported-wit/             # only for `tarawasm import`
└── dist/
    └── <world>.wasm              # the only final component
```

Language-specific binding and target directories are generated artifacts.
`tarawasm clean` removes only paths recorded in `.tarawasm/artifacts.json`; it
does not scan for `*.wasm` and does not delete user `target/`, `internal/`, or
other pre-existing files.

## Docker and Python dependencies

The image maps generated files to the bind-mounted project's UID/GID instead of
making the project world-writable. Python packages can be installed into the
project without rebuilding the image:

```console
docker run --rm -v "$PWD:/work" -w /work mandeser0/tarawasm:latest \
    pip install -r requirements.txt
docker run --rm -v "$PWD:/work" -w /work mandeser0/tarawasm:latest build
```

Packages persist in `.tarawasm/site-packages` and are reused by
`componentize-py`. Set `TARAWASM_PY_SITE_PACKAGES` consistently on install and
build to choose another location.

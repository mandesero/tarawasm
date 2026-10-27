# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases
use [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Fix starter generation for minimal WIT worlds across Python, Go, Rust and
  JavaScript: avoid missing Python interface bindings, unused Go interface
  imports and absent Rust export macros; keep empty JavaScript modules
  available to Jco's bundler.

## [0.4.0] - 2026-10-26

### Added

- Integration coverage for a wheel-installed CLI using a Docker Python toolchain:
  host-only packages stay isolated, while container-installed project packages
  remain available after cleanup and across fresh build containers.

- Python wheel/source packaging with the `tarawasm` console command and a
  GitHub release workflow for PyPI Trusted Publishing.

- `csharp` backend with WIT-generated user stubs, real C# bindings,
  locked .NET/NuGet dependencies and verified Component Model publication,
  using an experimental componentize-dotnet/NativeAOT-LLVM toolchain.
  Supports direct world exports, interfaces, external versioned WIT packages and
  synchronous resources, without a Tarantool dependency.
- C# toolchain discovery/setup/selection/locks, cached compile-capability probe,
  Linux amd64 Docker target and inclusion in the full `all` image. Pin .NET SDK
  10.0.402, componentize-dotnet 0.8.0-preview00011, NativeAOT-LLVM
  10.0.0-rc.1.26306.1, wit-bindgen 0.58.0 and WASI SDK 29.0. Local macOS builds
  report the upstream compiler limitation and require an explicit Docker choice.
- C# example and regression/integration coverage for bindings, locks, path
  overrides, cleanup, failure recovery, Unicode, results and resource lifecycles.

- Local/Docker toolchain selection, first-use discovery, per-tool versions and
  compatibility diagnostics, custom binary paths and images, and project locks.
- `toolchain setup` plans or executes pinned installation for one language or
  all languages; automatic local installation supports macOS on Apple Silicon/Intel
  and glibc Linux x86-64 with apt-get, dnf, or yum (Debian/Ubuntu/Astra and
  Fedora/CentOS/RED OS families).
- Separate `base`, `python`, `go`, `js`, `rust`, and `c` Docker build targets,
  with the full `all` target retained for compatibility and testing.
- Noninteractive setup and JSON diagnostics for CI.
- Integration coverage for saved local profiles across all five languages.
- JS integration coverage for npm archive installation, bundling, hyphenated WIT
  exports and resource methods, HTTP features, compiler metadata, stripping,
  validation, and execution in native and Docker environments.

### Changed

- Publish language toolchain images from master as `latest-{language}` and
  tagged releases as `{git-tag}-{language}`, avoiding overwrites of catalog
  release tags. New default Docker selections use `latest-{language}`;
  existing explicit selections and digest locks are preserved.

- Document dependency installation for pip CLI with Docker toolchains separately
  from the Full-Docker shell function, including project-local Python/JavaScript
  installs and all supported language workflows.

- Reorganize the README around pip/local or Docker toolchains and full Docker,
  with a shared quick start, language notes and a separate usage reference.

- Recommend Go 1.27.2 and TinyGo 0.43.0 with Binaryen 133. Keep TinyGo 0.42
  compatible with Binaryen 116, and preserve user-selected build flags and the
  ordinary asyncify build mode.
- Install a verified external Binaryen release with TinyGo on Linux amd64 and
  macOS arm64/amd64; publish the complete compiler/optimizer tree only after both
  downloads and checksum checks succeed. Go/TinyGo/Binaryen checksums are keyed
  by version, OS and architecture and shared with source-built Docker images.
- Go discovery checks the selected wasm-opt version and pins that same path via
  WASMOPT during local CLI operations, with explicit environment overrides taking
  priority.
- JavaScript builds bundle local and npm ESM dependencies by default.
- The JS Docker image includes npm and npx from the complete Node distribution.

- CLI runtime dependencies contain only Click; compiler packages
  are installed separately as toolchain/development dependencies.
- Local installers use managed user directories and skip compatible tools by
  default; `--upgrade` refreshes unlocked older tools without downgrading newer
  compatible binaries.
- Updated pinned compiler/Wasm/JS releases: Go 1.27.1, TinyGo 0.42.0, Rust 1.99.0,
  Node 24.21.0 LTS, WASI SDK 34 (Clang 23.1.0), wasm-tools 1.261.0, wkg 0.16.1,
  wit-bindgen 0.62.0, componentize-py 0.25.1, jco 1.37.0, componentize-js 0.23.0,
  with preview2-shim retained at 0.17.8 for the embedded splicer compatibility. Wasmtime is pinned to 49.0.2 for test environments.
- WIT dependency commands use `wkg fetch` with the wkg 0.16 directory syntax.
  Explicit updates regenerate the lock with rollback because upstream 0.16.1
  `update` panics after writing it.
- Linux TinyGo/SDK installation uses checksum-verified archives without requiring
  dpkg-deb on RPM systems.

### Fixed

- Preserve WIT dependency locks on failed resolution/update and require explicit
  migration of legacy nested locks for wkg 0.16.1.

- Go scaffolds preserve hyphenated WIT import paths, qualify named world and
  interface types, and match the tuple/result representations of wit-bindgen-go
  0.7.0, including nested types and long heterogeneous tuples. Numeric-only
  exports no longer receive an unused `cm` import from their WASI imports.
- Go regression fixtures compile real bindings and TinyGo components through
  CLI init/bind/build, strip and validate, including custom module paths and
  `--versioned`/`--generate-wit` binding flags.
- Python builds preserve the source directory for imports, including nested
  `source` paths and `--src` overrides, while retaining project bindings,
  persistent packages, and additional `--python-path` arguments.
- JavaScript feature selectors form one effective set with user arguments taking
  priority over the stdio-only default.
- Generated JS exports, interfaces, and resource methods use camelCase WIT
  bindings, with PascalCase resource classes.

### Removed

- Nuitka standalone CLI builds, `make build`, and the standalone test mode.
  Run the CLI with `python3 -m tarawasm.cli` or through Docker.

## [0.3.0] - 2026-08-08

### Added

- WIT-first `init`, `import`, `bind`, `build`, dependency management, and
  project workflows.
- Managed project layouts, atomic output publication, recorded artifacts, dry
  runs, and safe cleanup.
- Support for world-level WIT type declarations.
- The BSD-2-Clause license, contribution guide, and release changelog.

### Changed

- Aligned Go builds with TinyGo's `wasip2` requirements.
- Docker builds now preserve host ownership and project-installed Python
  dependencies.
- Expanded onboarding, project-layout, dependency, and example documentation.

## [0.2.0] - 2026-03-06

### Added

- A consistent common-option and tool-option boundary, including
  language-specific passthrough flags and `--tool-help`.
- Docker-mode linux/amd64 tests, upstream tool-repository integration tests,
  and language smoke tests.

### Changed

- Updated compiler, binding-generator, and Component Model toolchain
  dependencies.

### Removed

- The intermediate WIT exports JSON generation path.

### Fixed

- Guest-language file permissions and protection of existing `main.*` source
  files.
- WIT export handling for hyphenated names, nested types, docstrings, and
  functions without return values.
- JavaScript Component Model tool compatibility.

## [0.1.0] - 2025-07-01

### Added

- Component builds for Python, Go, JavaScript, Rust, and C/C++.
- Language-specific starter sources and working examples.
- Docker image builds and Docker Hub publication.
- The `strip` command for removing WebAssembly component metadata.
- Build, test, formatting, linting, and static type-checking workflows.

### Changed

- Refactored CLI configuration and build/test integration for the first stable
  release.

[Unreleased]: https://github.com/mandesero/tarawasm/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/mandesero/tarawasm/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/mandesero/tarawasm/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/mandesero/tarawasm/releases/tag/v0.1.0

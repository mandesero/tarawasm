# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases
use [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- Preserve WIT dependency locks on failed resolution/update and require explicit migration of legacy nested locks for wkg 0.16.1.

### Added

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

### Changed

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

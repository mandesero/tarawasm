# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases
use [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

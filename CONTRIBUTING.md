# Contributing

Thank you for helping improve tarawasm. Open an issue before making a breaking
or cross-cutting change so the command-line contract, generated project layout,
and effects on every supported language can be agreed before implementation.

## Development setup

Tarawasm requires Python 3.10 or newer. Install the development dependencies
from the repository root:

```sh
python3 -m pip install -r requirements-dev.txt
```

The complete standalone toolchain can be installed with:

```sh
sudo make install
make check
```

The installation script writes system locations and may download compilers and
binding generators. Use the Docker image described in the README when changing
the host toolchain is undesirable.

## Making changes

Keep WIT handling independent of a particular guest language. A change to a
shared command or generated project should behave consistently for Python, Go,
JavaScript, Rust, and C/C++ unless the difference is documented and covered by
a language-specific test.

Preserve the safety guarantees of generated projects: do not overwrite user
source by default, publish build output atomically, and make cleanup remove only
artifacts recorded as generated. Update README.md and CHANGELOG.md for every
user-visible modification.

## Local validation

Run formatting, linting, type checks, and the non-Docker test suite:

```sh
pre-commit run --all-files --color always
make check
make build
PYTHONPATH=. python3 -m pytest -k "not cli:docker" -vv
```

Changes to Docker behavior or language toolchains should also run the matching
linux/amd64 integration checks:

```sh
make test-docker-amd64
make test-upstream-amd64
```

These checks build an image and may download upstream repositories, so note in
the pull request when one cannot be run locally.

## Submitting changes

Keep each commit focused on one feature or maintenance task. Include tests for
behavior changes and summarize the validation performed in the pull request.
Do not commit build output, generated bindings, virtual environments, caches,
or other ignored artifacts.

Contributions are accepted under the repository's
[BSD-2-Clause license](LICENSE). The collective copyright holder name
`tarawasm contributors` refers to the contributors recorded in the
repository's Git history.

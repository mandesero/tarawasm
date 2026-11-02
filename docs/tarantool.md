# Tarantool integration

## Create and build

```sh
tarawasm init --target tarantool --lang python \
  --package acme:orders@1.2.3 --world user-service ./orders
cd orders
```

`--package` and `--world` name the generated WIT package and world. Defaults are
`example:app@0.1.0` and `app`. The world has no application exports: Python,
JavaScript, Go and C receive SDK includes; Rust and C# obtain host imports from
their SDK package. Go also receives its required versioned WASI imports.

Add your interfaces, types and exports to `wit/app.wit`, implement them in your
source, then run `tarawasm bind` and `tarawasm build`. The output is
`dist/<world>.wasm`. For subsequent WIT changes, `tarawasm clean` clears generated
bindings before `bind` and `build`, preserving source, WIT, SDK/runtime inputs and
language dependency locks.

To use an existing contract, supply `--wit ./wit --world <world>` instead of
`--package`. Tarawasm copies it with the SDK's resolved WIT dependencies; it does
not rename its package. C/C++ receives raw WIT bindings and ordinary stubs;
there is no released C SDK.

The application owns Tarantool configuration and execution through
`require('wasm')`. Tarawasm builds components and installs the native library as
`.rocks/lib/tarantool/wasm.so`, also on macOS (the downloaded `.dylib` is renamed).
Runtime artifacts require Tarantool 3.6+ and support macOS arm64 and glibc Linux
x86-64. C# uses a Linux amd64 toolchain. Go requires TinyGo 0.43+ and synchronous
panic unwinding; scheduler/panic overrides are rejected for this profile.

## Python SSL and asyncio DNS

A generated Python project imports the SDK SSL contract and calls
`twr_python_sdk.install(ports=["ssl", "asyncio_dns"])` before application imports.
Keep this initialization before modules that consume `ssl` or `asyncio`.
The SSL contract is copied into `wit/deps/adder/package.wit`; the import resolves
locally during `bind` and `build`. With `--wit`, your contract is preserved: include
`import docs:adder/ssl-bio@0.1.3;` in the selected world to receive the generated
initialization. Its dependency is already installed. The SDK expects the import
name `ssl-bio`; a renamed import is rejected.

The DNS adapter lets `asyncio` resolve names through WASI without executor
threads. The resolver itself blocks the guest event loop; the Tarantool host
must allow name lookup (`allow_ip_name_lookup = true` in `wasm.load` options).

Tarantool needs OpenSSL 3 runtime libraries for TLS (`libssl3` on Ubuntu 22.04,
`brew install openssl@3` on macOS). The native module loads them dynamically.
See the [SDK SSL port](https://github.com/tarantool/tarantool-wasm-rs/blob/v0.1.0/guests/python/ports/ssl/README.md)
for permissions, certificate handling and compatibility limits.

Python/Tarantool builds automatically strip custom sections and apply the locked
SDK's supplied `patch_socket_errors` implementation before validating and
publishing the component.
This fixes the pinned componentize-py 0.25.1 socket-errno mapper. Debug/custom
metadata is removed; other Python builds retain their normal behavior. An
unsupported mapper fails the build and preserves the previous successful output.
Future release entries can disable the patch once their toolchain fixes the issue.

### Build-time imports and runtime calls

Componentize-py executes `main.py` and its top-level imports while building the
component, then saves the initialized Python state in the `.wasm`. Exported
methods run later, when Tarantool loads and calls the component. Tarantool host
functions are available at that second stage.

This matters even for an import that does not appear to access the network.
For example, `urllib3` reads `ssl.OPENSSL_VERSION` during import. The SDK obtains
that value by calling `docs:adder/ssl-bio@0.1.3#backend` in Tarantool. A top-level
`import urllib3` therefore fails during componentization with
`called trapping stub: docs:adder/ssl-bio@0.1.3#backend`. Having the SSL WIT in
`deps/` supplies the contract for binding; it does not provide a running
Tarantool host during the build.

Move imports that query host capabilities into an exported method. Make their
sources available at runtime with `twr_python_sdk.freeze_packages("urllib3")`
at module scope, before the package's first import. This SDK function stores
the package's Python sources and resources in the component without executing
its imports. It does not install packages, resolve dependencies or make native
host extensions usable in Wasm. Pass top-level package names; additional pure
Python dependencies can be frozen in the same call.

Ordinary imports that do not call host functions can stay at module scope.
In particular, import the standard-library modules needed by a deferred package
during the build. Otherwise they may be absent from the saved interpreter and
the runtime import fails with `ModuleNotFoundError`, even though those modules
exist in the build Python installation. The required imports depend on the
package version and the features your application uses.

### HTTP client example with urllib3

The following example uses SDK 0.1.0 and `urllib3` 2.8.0. Install the package in
a project-local directory and explicitly include that directory on the build
Python path; this works with local and Docker toolchains:

```sh
tarawasm init --target tarantool --lang python ./http-app
cd http-app
python -m pip install --target .tarawasm/site-packages "urllib3==2.8.0"
```

Add the `get` export to `wit/app.wit`, retaining the SDK includes and import:

```wit
package example:app@0.1.0;

world app {
  include tarantool:tarantool/guest@0.2.0;
  import docs:adder/ssl-bio@0.1.3;
  export get: func(host: string) -> string;
}
```

Replace `main.py` with:

```python
import twr_python_sdk
twr_python_sdk.install(ports=["ssl", "asyncio_dns"])

# Include stdlib dependencies before the interpreter state is saved.
import hmac
import importlib.metadata
import json
import mimetypes
import queue
import zlib

import wit_world
from twr_python_sdk import tarantool

# Include urllib3 without executing its SSL capability queries at build time.
twr_python_sdk.freeze_packages("urllib3")


class WitWorld(wit_world.WitWorld):
    def get(self, host: str) -> str:
        import urllib3

        with urllib3.PoolManager() as http:
            response = http.request("GET", host)
            body = response.data.decode("utf-8")
        tarantool.log.write(tarantool.LogLevel.INFO, body)
        return body
```

Here `hmac`, `importlib.metadata`, `json`, `mimetypes`, `queue` and `zlib` are
imported to include dependencies of the frozen `urllib3` package. Keep these
imports even though `main.py` does not call those modules directly. `urllib3`
itself is imported inside `get`, where SSL host calls can run. The method takes
`self` and returns decoded text to match the WIT `string` result; an
`HTTPResponse` object cannot be returned as that result.

Regenerate bindings and build:

```sh
tarawasm clean
tarawasm bind
tarawasm build -- --python-path .tarawasm/site-packages
```

Bindings are generated in `wit_world/`. `bind` preserves the application code
in `main.py`; after future WIT changes, update its implementations yourself.
The resulting component is `dist/app.wasm`.

### HTTPS certificates and the guest environment

Load the HTTP example from the application directory in a configured Tarantool
instance. If it needs no inherited host environment, use:

```lua
local wasm = require('wasm')
local m = wasm.load('dist/app.wasm', {inherit_env = false})
local app = wasm.bind(m)
local body = app.get('https://tarantool.io')
print(body)
wasm.drop(m)
```

The SDK uses the host OpenSSL default CA store unless the guest environment
overrides its sources. The host must have a configured CA store; installing the
native module does not supply CA certificates. `inherit_env = false` disables
inheritance of all host environment variables and leaves TLS certificate and
hostname verification enabled. Required application variables can be passed
explicitly through the `env` option.

With the default environment inheritance, `SSL_CERT_FILE` and `SSL_CERT_DIR`
become guest paths. A file visible to the Tarantool process is accessible to
the guest only when exposed through `preopened_dirs`. For example, Tarantool on
macOS can set `SSL_CERT_FILE=/private/etc/ssl/cert.pem`. If that file is not
available inside the guest, the SDK ignores the missing override file but also
suppresses the host OpenSSL default CA-file source. With no other trusted
anchors, HTTPS fails with `CERTIFICATE_VERIFY_FAILED` and
`unable to get local issuer certificate`.

For an explicit CA bundle, place the trusted PEM file at `certs/ca.pem` in the
application directory and expose that directory read-only:

```lua
local wasm = require('wasm')
local m = wasm.load('dist/app.wasm', {
    inherit_env = false,
    env = {SSL_CERT_FILE = '/certs/ca.pem'},
    preopened_dirs = {
        {'./certs', '/certs', perms = 'ro'},
    },
})
local app = wasm.bind(m)
local body = app.get('https://tarantool.io')
print(body)
wasm.drop(m)
```

The first path in each `preopened_dirs` entry belongs to the host; the second
is the guest path used by Python. Both CA files and CA directories must follow
this mapping when selected through the guest environment.

## Install dependencies after checkout

Commit application source, WIT, configuration, `tarawasm.tarantool.lock.json` and
language dependency locks. Include `wit/deps/`, where `init` installs the SDK's
WIT contracts. `init` also installs the SDK and native library immediately;
`tarawasm clean` preserves them, so ordinary development needs no repeated setup.

The downloaded files under `.tarawasm/tarantool` and `.rocks` are ignored by
Git. After cloning the project onto another machine or checking it out in CI,
install those dependencies from the project lock with:

```sh
tarawasm tarantool setup
tarawasm doctor --lang python
```

Setup installs the release and platform recorded in the lock. SDK inputs under
`.tarawasm/tarantool` are available to both local and Docker compilers. Setup
preserves modified/unowned installation files and does not rewrite source, WIT
or language locks. `bind` and `build` verify inputs without installing/updating
SDKs.

The runtime platform defaults to the CLI host, including with
`--execution docker`. Select `--runtime-platform linux-x86_64` for Linux
deployment, or `--sdk-only` to omit the runtime. To change a managed platform,
use `tarawasm tarantool setup --runtime-platform linux-x86_64 --upgrade`.
`--sdk-only --upgrade` stops managing the runtime without deleting its file.
Here `--upgrade` changes platform management; it does not upgrade the SDK release.

## Choose a release

The installed release catalog is
[`tarawasm/tarantool-releases.json`](../tarawasm/tarantool-releases.json).
`tarawasm init --help` lists its verified releases and default. Select one with
`--tarantool-wasm-version <version>` during initialization. Unknown versions are
rejected; no command silently falls back to the latest upstream release.

Updating tarawasm can add supported releases and change the default for **new**
projects. Existing projects keep `lock.version`, its checksums and tool minimums.
Old catalog entries remain available for restoration. SDK/WIT/dependency migration
is explicit: initialize a separate project with the desired release, port your
application contract/source, resolve its language locks and run integration tests
before adopting it. Do not edit a lock's version alone or use `setup --upgrade`
as a release migration.

## Add a supported release (maintainers)

1. Inspect the assets and release notes in the
   [upstream releases](https://github.com/tarantool/tarantool-wasm-rs/releases).
   Download the SDK and each supported native module; compare their SHA256 with
   the published asset digests. Inspect the SDK's package manifests and WIT.
2. Append an entry under `releases` in the catalog. Preserve existing entries and
   record independent Go-module, NuGet, WIT and MessagePack versions, tool
   minimums, includes and artifact hashes. If newer compilers are needed, update
   the existing toolchain catalog and its verified tool-release checksums too. The Python dependency entry specifies
   its source URL, SHA256 and extracted directory. Shared installation paths are
   stable project-layout contracts, not settings to change for a new release.
3. Test the candidate without changing the default. Prepare the five native
   toolchains and Tarantool on Linux, then run:

   ```sh
   TARAWASM_TARANTOOL_IT=1 TARAWASM_TARANTOOL_WASM_VERSION=<version> \
     python -m pytest tests/test_tarantool_integration.py -k 'cli:python' -vv -ra
   ```

   Require all five SDK cases to pass without skips. They build an empty starter,
   add application exports, extend WIT with a record/optional interface and check
   real Tarantool data. Also verify the supported macOS runtime and CLI package
   formats (wheel/standalone).
4. Set `default` after compatibility is established. The focused
   `Tarantool integration` Ubuntu workflow validates the default for all five SDKs
   on PRs, master pushes and manual runs; a skipped SDK case fails its job.
5. Ship the catalog with a tarawasm release and describe compatibility changes.
   JSON-only updates assume the existing archive layout and SDK consumption API;
   a changed layout/API needs an implementation change and review as well.

# C# calculator component

This is a generic WIT library with `add` and `echo` exports. It has no Tarantool
dependencies. The toolchain is experimental: .NET SDK 10.0.402,
componentize-dotnet 0.8.0-preview00011, NativeAOT-LLVM 10.0.0-rc.1.26306.1,
wit-bindgen 0.58.0 and WASI SDK 29.0. Compilation is supported on Linux amd64;
macOS hosts must select Docker explicitly.

Build the image from the repository root, then copy this example:

```sh
docker buildx build --platform linux/amd64 --target csharp --load -t tarawasm:csharp .
cp -R examples/csharp /tmp/tarawasm-csharp
cd /tmp/tarawasm-csharp
tarawasm toolchain use csharp --mode docker --image tarawasm:csharp --project
tarawasm bind
tarawasm build
docker run --rm --platform linux/amd64 -v "$PWD:/work" -w /work tarawasm:csharp \
  wasm-tools validate dist/calculator.wasm
```

For local Linux amd64 use `tarawasm toolchain setup csharp --mode local
--install --yes`, then `tarawasm toolchain use csharp --mode local --project`.
`source`/`--src` names the `.csproj`; user implementations live in `src/`.
Keep `global.json`, `nuget.config` and `packages.lock.json` in version control.
Bind/build use locked restore; they do not update dependencies. `clean` preserves
these inputs and the implementation.

The result is a Component Model **library**, so its host calls exports. With a
compatible Wasmtime CLI that supports component function invocation:

```sh
wasmtime run --invoke 'add(19, 23)' dist/calculator.wasm
```

Alternatively, use Jco's WASI runtime (Node and Jco installed separately):

```sh
jco transpile dist/calculator.wasm -o transpiled --name calculator
printf '{"type":"module"}\n' > package.json
npm install --save-exact @bytecodealliance/preview2-shim@0.17.8
node --input-type=module -e "const c = await import('./transpiled/calculator.js'); console.log(c.add(19, 23)); console.log(c.echo('Привет 🌍'));"
```

Expected arithmetic result: `42`. The test suite additionally exercises a
neutral custom host, bidirectional records/lists/options/results, empty and NUL
strings, imported iterator disposal and exported resource disposal. This small
component does not establish support for arbitrary .NET applications or all
standard library APIs.

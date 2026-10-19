"""Capability discovery and managed installation for the experimental C# stack."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tarawasm.backends.base import BackendError

from .catalog import CATALOG, TOOLS
from .settings import ToolchainError


def capability_inputs(dotnet: str) -> list[Path]:
    from tarawasm.csharp import (
        BINDGEN_PACKAGE,
        LLVM_PACKAGE,
        bindgen,
        package_path,
        toolchain_home,
    )

    runtime_name = "runtime.wasi-wasm.microsoft.dotnet.ilcompiler.llvm"
    runtime = package_path(runtime_name)
    return [
        Path(dotnet).resolve(),
        bindgen(),
        package_path(LLVM_PACKAGE) / "tools/ilc",
        toolchain_home() / "wasi-sdk/bin/clang",
        package_path(BINDGEN_PACKAGE)
        / f"{BINDGEN_PACKAGE}.{CATALOG['csharp']['sdk']}.nupkg.sha512",
        runtime / f"{runtime_name}.{CATALOG['csharp']['llvm']}.nupkg.sha512",
        runtime / "runtimes/wasi-wasm/native-hidden/System.Private.CoreLib.dll",
        runtime / "runtimes/wasi-wasm/native-hidden/libbootstrapperdll.o",
        toolchain_home() / "wasi-sdk/share/wasi-sysroot/include/wasm32-wasip2/stdio.h",
        toolchain_home() / "wasi-sdk/share/wasi-sysroot/lib/wasm32-wasip2/libc.a",
    ]


def fingerprint(dotnet: str) -> str:
    # A content fingerprint survives Docker COPY and accepts an identical SDK
    # selected through toolchain set, without trusting its path or timestamp.
    values = []
    for path in capability_inputs(dotnet):
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        values.append(digest.hexdigest())
    return hashlib.sha256(json.dumps([CATALOG["csharp"], values]).encode()).hexdigest()


def capability(dotnet: str, env: dict[str, str]) -> dict:
    from tarawasm.csharp import bindgen, require_platform, run, toolchain_home

    try:
        require_platform()
        home = toolchain_home()
        if (
            not (home / "wasi-sdk/VERSION").is_file()
            or not (home / "capability.json").is_file()
        ):
            return {
                "status": "missing",
                "detail": "C# compiler packages/WASI SDK/compile probe are not prepared; run toolchain setup csharp --mode local --install --yes.",
            }
        version = run([str(bindgen()), "--version"], env=env).strip()
        if version not in {
            f"wit-bindgen {CATALOG['csharp']['wit_bindgen']}",
            f"wit-bindgen-cli {CATALOG['csharp']['wit_bindgen']}",
        }:
            raise BackendError(f"Incompatible C# bindings generator: {version}")
        if (home / "wasi-sdk/VERSION").read_text().split()[:1] != [
            CATALOG["csharp"]["wasi_sdk"]
        ]:
            raise BackendError(
                "C# requires its own WASI SDK 29.0; the C backend SDK is separate."
            )
        expected = fingerprint(dotnet)
        receipt = json.loads((home / "capability.json").read_text())
        wasm = (home / "probe.wasm").read_bytes()
        if receipt != {
            "fingerprint": expected,
            "component_sha256": hashlib.sha256(wasm).hexdigest(),
        }:
            raise BackendError(
                "C# compiler capability receipt is stale; rerun toolchain setup csharp --mode local --install --yes --upgrade."
            )
        if wasm[:8] != b"\0asm\x0d\0\x01\0":
            raise BackendError("C# capability probe is not a component.")
        return {
            "status": "ready",
            "detail": "pinned SDK/compiler/bindings/WASI SDK built a verified component (cached capability probe)",
            "components": CATALOG["csharp"],
        }
    except (BackendError, OSError, ValueError) as exc:
        return {
            "status": "incompatible",
            "detail": f"{exc} Prepare with toolchain setup csharp --mode local --install --yes --upgrade, or explicitly select Docker.",
        }


def prepare(dotnet: str) -> None:
    from tarawasm.csharp import (
        PROBE_WIT,
        build_project,
        implementation_files,
        project_files,
        require_platform,
        toolchain_home,
    )

    require_platform()
    home = toolchain_home()
    probe = home / "probe"
    probe.mkdir(parents=True, exist_ok=True)
    for name, content in project_files().items():
        path = probe / name
        path.write_text(content)
    wit = probe / "probe.wit"
    wit.write_text(PROBE_WIT)
    for name, content in implementation_files(wit, "probe").items():
        (probe / name).parent.mkdir(parents=True, exist_ok=True)
        (probe / name).write_text(content)
    import shutil

    from .discovery import managed_environment

    validator = shutil.which("wasm-tools", path=managed_environment()["PATH"])
    if not validator:
        raise ToolchainError(
            "wasm-tools is required to validate the C# capability probe."
        )
    output = home / "probe.wasm"
    build_project(
        dotnet,
        probe / "Component.csproj",
        wit,
        "probe",
        home / "probe-build",
        output,
        [],
        validator=validator,
    )
    (home / "capability.json").write_text(
        json.dumps(
            {
                "fingerprint": fingerprint(dotnet),
                "component_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            }
        )
    )


def install(root: Path, temporary: Path, env: dict[str, str]) -> None:
    from tarawasm.csharp import require_platform, toolchain_home

    from .installer import download, extract_archive, replace_release_tree

    require_platform()
    home = toolchain_home()
    home.mkdir(parents=True, exist_ok=True)
    version = TOOLS["dotnet"]["recommended"]
    archive = temporary / "dotnet.tar.gz"
    download(
        f"https://builds.dotnet.microsoft.com/dotnet/Sdk/{version}/dotnet-sdk-{version}-linux-x64.tar.gz",
        archive,
    )
    if hashlib.sha512(archive.read_bytes()).hexdigest() != TOOLS["dotnet"]["sha512"]:
        raise ToolchainError(".NET SDK SHA512 mismatch.")
    extracted = temporary / "dotnet"
    extract_archive(archive, extracted)
    replace_release_tree(extracted, root / "dotnet")
    wasi = CATALOG["csharp"]["wasi_sdk"]
    archive = temporary / "csharp-wasi.tar.gz"
    download(
        f"https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-{wasi.split('.')[0]}/wasi-sdk-{wasi}-x86_64-linux.tar.gz",
        archive,
        CATALOG["csharp"]["wasi_sha256"],
    )
    extract_archive(archive, temporary / "csharp-wasi")
    replace_release_tree(
        temporary / f"csharp-wasi/wasi-sdk-{wasi}-x86_64-linux", home / "wasi-sdk"
    )
    from tarawasm.csharp import project_files, run

    bootstrap = temporary / "restore"
    bootstrap.mkdir()
    for name, content in project_files().items():
        (bootstrap / name).write_text(content)
    restore_env = {
        **env,
        "NUGET_PACKAGES": str(home / "packages"),
        "DOTNET_CLI_HOME": str(home / "dotnet-home"),
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
    }
    dotnet = str(root / "dotnet/dotnet")
    run(
        [dotnet, "restore", str(bootstrap / "Component.csproj"), "--locked-mode"],
        env=restore_env,
        cwd=bootstrap,
    )
    prepare(dotnet)

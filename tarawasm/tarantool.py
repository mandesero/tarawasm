"""Install the released Tarantool guest SDK beside an application.

SDK files are project inputs, never build artifacts. All downloads and language
dependency resolution happen during explicit setup, before publishing files.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import zipfile
from contextlib import contextmanager
from importlib.resources import files as resource_files
from pathlib import Path

from tarawasm.backends import get_backend
from tarawasm.backends.base import BackendError, Command
from tarawasm.config import CONFIG_FILE, Config
from tarawasm.toolchains.installer import download, extract_archive
from tarawasm.toolchains.runtime import command_argv, executable
from tarawasm.wit import WitParser

CATALOG = json.loads(
    (resource_files("tarawasm") / "tarantool-releases.json").read_text(encoding="utf-8")
)
LOCK = Path(CATALOG["paths"]["lock"])
SDK = Path(CATALOG["paths"]["sdk"])
RUNTIME = Path(CATALOG["paths"]["runtime"])


def release(version: str | None = None) -> dict:
    version = CATALOG["default"] if version is None else version
    try:
        return CATALOG["releases"][version]
    except KeyError as exc:
        raise BackendError(
            f"No verified Tarantool-Wasm release {version}; supported: {', '.join(CATALOG['releases'])}."
        ) from exc


def host_platform() -> str | None:
    return {
        ("Darwin", "arm64"): "macos-arm64",
        ("Linux", "x86_64"): "linux-x86_64",
    }.get((platform.system(), platform.machine()))


def _asset(suffix: str, destination: Path, version: str) -> None:
    name = f"tarantool-wasm-{version}-{suffix}"
    download(
        f"{CATALOG['base_url']}/v{version}/{name}",
        destination,
        release(version)["checksums"][suffix],
    )


def _unzip(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            path = Path(item.filename)
            if path.is_absolute() or ".." in path.parts:
                raise BackendError("Unsafe SDK archive member.")
        source.extractall(destination)


def _run(argv: list[str], root: Path) -> None:
    env = {**os.environ, **({"GOTOOLCHAIN": "local"} if argv[0] == "go" else {})}
    subprocess.run(command_argv(tuple(argv)), cwd=root, env=env, check=True)


def install_sdk(language: str, staging: Path, version: str) -> Path:
    """Prepare the selected released package and its portable Python dependency."""
    archive = staging / "sdk.tar.gz"
    _asset("sdk.tar.gz", archive, version)
    extract_archive(archive, staging / "bundle")
    bundle = staging / "bundle" / f"tarantool-wasm-{version}-sdk"
    destination = staging / "project" / SDK
    destination.mkdir(parents=True)
    sdk_language = "python" if language == "c" else language
    if language != "c":
        package = next(
            path
            for path in (bundle / "packages" / language).iterdir()
            if path.suffix != ".md"
        )
        target = destination / language
        if language in {"python", "csharp"}:
            if language == "python":
                _unzip(package, target)
                msgpack = staging / "msgpack.tar.gz"
                dependency = release(version)["msgpack"]
                download(dependency["url"], msgpack, dependency["sha256"])
                extract_archive(msgpack, staging / "msgpack")
                source = staging / "msgpack" / dependency["directory"]
                shutil.copytree(source / "msgpack", target / "msgpack")
                shutil.copyfile(source / "COPYING", target / "msgpack/COPYING")
            else:
                target.mkdir()
                shutil.copyfile(package, target / package.name)
        else:
            extract_archive(package, staging / "package")
            folder = next((staging / "package").iterdir())
            shutil.copytree(folder, target)
    shutil.copytree(bundle / "wit" / sdk_language / "deps", destination / "wit-deps")
    return destination


def _default_wit(language: str, package: str, world: str, version: str) -> str:
    includes = "".join(
        f"  include {name};\n" for name in release(version)["includes"][language]
    )
    python = release(version).get("python", {})
    if language == "python" and python.get("ssl_import"):
        includes += f"  import {python['ssl_import']};\n"
    return f"package {package};\n\nworld {world} {{\n{includes}}}\n"


def _configure_language(language: str, root: Path, files: dict, version: str) -> None:
    """Use each package's normal consumption mechanism; no compiler wrappers."""
    spec = release(version)
    module = spec["go_module"]
    go_version = spec["go_version"]
    nuget_version = spec["nuget_version"]
    if language == "go":
        files[Path("go.mod")] += (
            f"\nrequire {module} v{go_version}\n" f"replace {module} => ./{SDK}/go\n"
        )
    elif language == "rust":
        files[Path("Cargo.toml")] = files[Path("Cargo.toml")].replace(
            "[dependencies]\n",
            f'[dependencies]\ntarantool-wasm = {{ path = "{SDK}/rust" }}\n',
        )
    elif language == "csharp":
        files[Path("Component.csproj")] = files[Path("Component.csproj")].replace(
            "  <ItemGroup>",
            f'  <ItemGroup>\n    <PackageReference Include="Tarantool.Wasm" Version="[{nuget_version}]" />',
            1,
        )
        files[Path("nuget.config")] = files[Path("nuget.config")].replace(
            "    <clear />",
            f'    <clear />\n    <add key="tarantool" value="{SDK}/csharp" />',
        )
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        (
            path.write_text(content)
            if isinstance(content, str)
            else path.write_bytes(content)
        )
    if language == "go":
        from tarawasm.toolchains.catalog import CATALOG

        _run(
            [
                "go",
                "get",
                "-tool",
                "go.bytecodealliance.org/cmd/wit-bindgen-go@v"
                + CATALOG["packages"]["wit-bindgen-go"],
            ],
            root,
        )
        _run(
            [
                "go",
                "get",
                "go.bytecodealliance.org@v" + CATALOG["packages"]["wit-bindgen-go"],
            ],
            root,
        )
        _run(["go", "mod", "download", "all"], root)
    elif language == "rust":
        _run(["cargo", "generate-lockfile"], root)
        _run(["cargo", "component", "bindings"], root)
        (root / "src/bindings.rs").unlink(missing_ok=True)
    elif language == "csharp":
        _run(
            [
                "dotnet",
                "restore",
                "--use-lock-file",
                "--force-evaluate",
                "-p:RestoreLockedMode=false",
                "--configfile",
                "nuget.config",
            ],
            root,
        )


def _cargo_wit_dependencies(wit: Path) -> str:
    entries = []
    for package in sorted((wit / "deps").iterdir()):
        if package.is_dir():
            text = "\n".join(path.read_text() for path in sorted(package.glob("*.wit")))
        elif package.suffix == ".wit":
            text = package.read_text()
        else:
            text = subprocess.check_output(
                [executable("wasm-tools"), "component", "wit", str(package)], text=True
            )
        name = re.search(r"^\s*package\s+([^@;\s]+)", text, re.MULTILINE)
        if not name:
            raise BackendError(f"Cannot determine WIT package name: {package}.")
        path = package.relative_to(wit.parent).as_posix()
        entries.append(f"{json.dumps(name[1])} = {{ path = {json.dumps(path)} }}\n")
    return "".join(entries)


def project_files(
    language: str,
    *,
    wit: Path | None,
    world: str | None,
    version: str,
    runtime_platform: str | None,
    sdk_only: bool,
    package: str | None = None,
) -> dict[Path, bytes]:
    release(version)
    if package is not None and wit:
        raise BackendError("Use --package only when generating WIT, without --wit.")
    if package is not None and not re.fullmatch(r"[^\s;{}]+:[^\s;{}]+", package):
        raise BackendError("--package must be a WIT package identifier.")
    if world == "":
        raise BackendError("--world must be a WIT identifier.")
    if not sdk_only and runtime_platform not in {"macos-arm64", "linux-x86_64"}:
        raise BackendError(
            "No runtime for this host. Select --runtime-platform or --sdk-only."
        )
    tool_requirements(language, version)
    with tempfile.TemporaryDirectory(prefix="tarawasm-tarantool-") as directory:
        staging = Path(directory)
        if not wit:
            identity = staging / "identity.wit"
            identity.write_text(
                f"package {package or 'example:app@0.1.0'}; world {world or 'app'} {{}}"
            )
            selected = WitParser().parse(identity).select_world(world or "app")
            if package and selected.package != package:
                raise BackendError("--package must be a WIT package identifier.")
        installed = install_sdk(language, staging, version)
        project = staging / "project"
        wit_dir = project / "wit"
        wit_dir.mkdir()
        if wit:
            if wit.is_dir():
                for source in wit.rglob("*"):
                    if source.is_file() and source.suffix in {".wit", ".wasm"}:
                        destination = wit_dir / source.relative_to(wit)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(source, destination)
            else:
                shutil.copyfile(wit, wit_dir / wit.name)
        else:
            (wit_dir / "app.wit").write_text(
                _default_wit(
                    language, package or "example:app@0.1.0", world or "app", version
                )
            )
        for source in (installed / "wit-deps").rglob("*"):
            if source.is_file():
                destination = (
                    wit_dir / "deps" / source.relative_to(installed / "wit-deps")
                )
                if (
                    destination.exists()
                    and destination.read_bytes() != source.read_bytes()
                ):
                    raise BackendError(
                        f"WIT dependency conflicts with SDK: {destination.relative_to(project)}"
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read_bytes())
        selected = (
            WitParser()
            .parse(wit_dir)
            .select_world(world or ("app" if not wit else None))
        )
        backend = get_backend(language)
        # C# needs the real staged WIT to generate its implementations.
        files = backend.initialize_files(selected, wit_dir, project)
        if language == "python":
            python = release(version).get("python", {})
            ssl = python.get("ssl_import")
            if ssl:
                interface, _, interface_version = ssl.rpartition("@")
                package_name, _, interface_name = interface.rpartition("/")
                matches = [
                    item
                    for item in selected.imports
                    if item.interface
                    and item.interface.name == interface_name
                    and item.interface.package == f"{package_name}@{interface_version}"
                ]
                if matches:
                    if matches[0].name not in {
                        ssl,
                        interface_name,
                    } and not re.fullmatch(r"interface-\d+", matches[0].name):
                        raise BackendError(
                            f"Python SDK requires the SSL import name {interface_name}."
                        )
                    main = files[Path("main.py")]
                    assert isinstance(main, str)
                    files[Path("main.py")] = (
                        "import twr_python_sdk\n"
                        f"twr_python_sdk.install(ports={python['ports']!r})\n\n" + main
                    )
        if language == "rust":
            # Cargo resolves external WIT packages independently of wasm-tools.
            cargo = files[Path("Cargo.toml")]
            assert isinstance(cargo, str)
            files[Path("Cargo.toml")] = cargo + _cargo_wit_dependencies(wit_dir)
        shutil.rmtree(installed / "wit-deps")
        _configure_language(language, project, files, version)
        conf = Config(
            language,
            selected.name,
            Path("wit"),
            selected.package,
            backend.default_source,
            Path("dist") / f"{selected.name}.wasm",
            project / CONFIG_FILE,
        )
        conf.save()
        if not sdk_only:
            suffix = (
                "macos-arm64.dylib"
                if runtime_platform == "macos-arm64"
                else "linux-x86_64.so"
            )
            (project / RUNTIME).parent.mkdir(parents=True)
            _asset(suffix, project / RUNTIME, version)
        result = {
            path.relative_to(project): path.read_bytes()
            for path in project.rglob("*")
            if path.is_file() and path.relative_to(project).parts[0] != "obj"
        }
        result[LOCK] = _lock(
            language, result, None if sdk_only else runtime_platform, version
        )
        return result


def _lock(
    language: str, files: dict, runtime_platform: str | None, version: str
) -> bytes:
    data = {
        "schema_version": 1,
        "version": version,
        "language": language,
        "wit_package": release(version)["wit_package"],
        "sdk_sha256": release(version)["checksums"]["sdk.tar.gz"],
        "runtime_platform": runtime_platform,
        "files": {
            str(path): hashlib.sha256(content).hexdigest()
            for path, content in files.items()
            if SDK in path.parents or path == RUNTIME
        },
    }
    return (json.dumps(data, indent=2) + "\n").encode()


def environment_files(
    language: str, runtime_platform: str | None, version: str
) -> dict[Path, bytes]:
    """Restore SDK/runtime inputs without regenerating the application's WIT/source."""
    if runtime_platform not in {None, "macos-arm64", "linux-x86_64"}:
        raise BackendError("Unsupported Tarantool runtime platform.")
    with tempfile.TemporaryDirectory(prefix="tarawasm-tarantool-setup-") as directory:
        staging = Path(directory)
        sdk = install_sdk(language, staging, version)
        shutil.rmtree(sdk / "wit-deps")
        project = staging / "project"
        if runtime_platform:
            suffix = (
                "macos-arm64.dylib"
                if runtime_platform == "macos-arm64"
                else "linux-x86_64.so"
            )
            (project / RUNTIME).parent.mkdir(parents=True)
            _asset(suffix, project / RUNTIME, version)
        files = {
            path.relative_to(project): path.read_bytes()
            for path in project.rglob("*")
            if path.is_file()
        }
        files[LOCK] = _lock(language, files, runtime_platform, version)
        return files


def check_destinations(root: Path, files: dict) -> None:
    for relative in files:
        if any(
            (root / parent).is_symlink() for parent in (relative, *relative.parents)
        ):
            raise BackendError(
                f"Refusing symlinked Tarantool installation path: {relative}."
            )


def locked_files(conf: Config, *, verify: bool = True) -> dict | None:
    path = conf.project_root / LOCK
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError) as exc:
        raise BackendError(f"Cannot read Tarantool SDK lock: {exc}") from exc
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != 1
        or not isinstance(data.get("version"), str)
        or data.get("language") != conf.language
        or not isinstance(data.get("files"), dict)
        or data.get("runtime_platform") not in {None, "macos-arm64", "linux-x86_64"}
    ):
        raise BackendError("Invalid or incompatible Tarantool SDK lock.")
    spec = release(data["version"])
    if (
        data.get("sdk_sha256") != spec["checksums"]["sdk.tar.gz"]
        or data.get("wit_package") != spec["wit_package"]
    ):
        raise BackendError("Invalid or incompatible Tarantool SDK lock.")
    for relative, expected in data["files"].items():
        if (
            not isinstance(relative, str)
            or not isinstance(expected, str)
            or not re.fullmatch("[0-9a-f]{64}", expected)
        ):
            raise BackendError("Invalid Tarantool SDK input checksum.")
        part = Path(relative)
        if (
            part.is_absolute()
            or ".." in part.parts
            or not (SDK in part.parents or part == RUNTIME)
        ):
            raise BackendError("Unsafe path in Tarantool SDK lock.")
        if part == RUNTIME or not verify:
            continue  # A build may target a different runtime platform.
        installed = conf.project_root / part
        if (
            not installed.is_file()
            or hashlib.sha256(installed.read_bytes()).hexdigest() != expected
        ):
            raise BackendError(f"Missing or modified Tarantool SDK input: {relative}.")
    marker = {
        "python": SDK / "python/_tarantool.py",
        "js": SDK / "js/src/index.js",
        "go": SDK / "go/go.mod",
        "rust": SDK / "rust/Cargo.toml",
        "csharp": SDK / f"csharp/Tarantool.Wasm.{spec['nuget_version']}.nupkg",
    }.get(conf.language)
    if marker and str(marker) not in data["files"]:
        raise BackendError("Incomplete Tarantool SDK lock.")
    if data["runtime_platform"]:
        suffix = (
            "macos-arm64.dylib"
            if data["runtime_platform"] == "macos-arm64"
            else "linux-x86_64.so"
        )
        if data["files"].get(str(RUNTIME)) != spec["checksums"][suffix]:
            raise BackendError("Incomplete or incompatible Tarantool runtime lock.")
    return data


def tool_requirements(language: str, version: str | None = None) -> None:
    from tarawasm.toolchains.catalog import version_tuple

    requirement = release(version)["minimum_tools"].get(language)
    if requirement:
        tool, minimum = requirement
        output = subprocess.check_output(
            [executable(tool), "version" if tool == "tinygo" else "--version"],
            text=True,
        )
        found = re.search(r"\d+\.\d+\.\d+", output)
        if found is None or version_tuple(found[0]) < version_tuple(minimum):
            raise BackendError(f"Tarantool SDK requires {tool} >= {minimum}.")


def build_args(conf: Config, args: list[str]) -> list[str]:
    data = locked_files(conf)
    if data is None:
        return args
    tool_requirements(conf.language, data["version"])
    if conf.language == "python":
        return ["--python-path", str(conf.project_root / SDK / "python"), *args]
    if conf.language == "rust":
        return ["--locked", *args]
    if conf.language == "go":
        if any(arg.startswith(("-scheduler", "-panic-unwind")) for arg in args):
            raise BackendError("Tarantool SDK manages -scheduler and -panic-unwind.")
        return ["-scheduler=none", "-panic-unwind=explicit", *args]
    return args


def postprocess_commands(conf: Config, output: Path) -> tuple[Command, ...]:
    """Apply SDK-owned Python compatibility fixes before component publication."""
    if conf.language != "python":
        return ()
    data = locked_files(conf)
    if data is None:
        return ()
    script = release(data["version"]).get("python", {}).get("patch_socket_errors")
    if not script:
        return ()
    relative = SDK / "python" / script
    if str(relative) not in data["files"]:
        raise BackendError("Python SDK socket patch is not pinned in the project lock.")
    return (
        Command(("wasm-tools", "strip", "--all", str(output), "-o", str(output))),
        Command(
            ("python3", "-I", "-B", str(conf.project_root / relative), str(output))
        ),
    )


def bind_commands(conf: Config, commands: tuple[Command, ...]) -> tuple[Command, ...]:
    if locked_files(conf) is None:
        return commands
    if conf.language == "go":
        command = commands[-1]
        return (Command(command.argv, {**command.env, "GOFLAGS": "-mod=readonly"}),)
    return commands


def build_command(backend, conf: Config, **kwargs) -> Command:
    kwargs["tool_args"] = build_args(conf, kwargs["tool_args"])
    command = backend.build_command(conf, **kwargs)
    if conf.language == "go" and (conf.project_root / LOCK).is_file():
        return Command(command.argv, {**command.env, "GOFLAGS": "-mod=readonly"})
    return command


@contextmanager
def dependency_locks(conf: Config):
    """Refuse implicit resolver changes before publishing a built component."""
    if not (conf.project_root / LOCK).is_file():
        yield
        return
    names = {
        "go": ("go.mod", "go.sum"),
        "rust": ("Cargo.lock", "Cargo-component.lock"),
        "csharp": ("packages.lock.json",),
    }.get(conf.language, ())
    before = {}
    for name in names:
        path = conf.project_root / name
        optional = conf.language == "rust" and name == "Cargo-component.lock"
        if path.is_symlink() or (
            not path.is_file() and (path.exists() or not optional)
        ):
            raise BackendError(
                f"Missing or symlinked dependency lock: {name}. Restore it before bind/build."
            )
        before[path] = (
            (path.read_bytes(), path.stat().st_mode)
            if path.is_file()
            else (None, 0o644)
        )
    try:
        yield
    finally:
        changed = []
        for path, (content, mode) in before.items():
            if content is None:
                if path.is_symlink() or path.exists():
                    path.unlink()
                    changed.append(path.name)
                continue
            if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
                fd, name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
                recovery = Path(name)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(content)
                recovery.chmod(mode)
                try:
                    os.replace(recovery, path)
                except OSError as exc:
                    raise BackendError(
                        f"Cannot restore {path}; recover it from {recovery}."
                    ) from exc
                changed.append(path.name)
        if changed:
            raise BackendError(
                f"Dependency locks changed during bind/build and were restored: {', '.join(changed)}. Resolve dependencies explicitly."
            )


def inspect_inputs(conf: Config, report: dict) -> None:
    """Extend doctor with SDK integrity and the SDK's stricter tool minimums."""
    if not (conf.project_root / LOCK).exists():
        return
    from tarawasm.toolchains.catalog import version_tuple

    detail = "project SDK inputs verified"
    status = "ready"
    version = "unknown"
    requirement = None
    try:
        data = locked_files(conf)
        if data:
            version = data["version"]
            requirement = release(version)["minimum_tools"].get(conf.language)
        if data and data["runtime_platform"]:
            installed = conf.project_root / RUNTIME
            expected = data["files"].get(str(RUNTIME))
            if (
                not installed.is_file()
                or hashlib.sha256(installed.read_bytes()).hexdigest() != expected
            ):
                raise BackendError(
                    "Missing or modified .rocks/lib/tarantool/wasm.so; run tarawasm tarantool setup."
                )
    except (BackendError, OSError) as exc:
        status, detail = "incompatible", str(exc)
    if requirement:
        tool, minimum = requirement
        for row in report["tools"]:
            if (
                row["tool"] == tool
                and row.get("version")
                and version_tuple(row["version"]) < version_tuple(minimum)
            ):
                row.update(
                    status="incompatible", detail=f"Tarantool SDK requires >= {minimum}"
                )
                status = "incompatible"
    report["tools"].append(
        {
            "tool": "tarantool-sdk",
            "mode": "project",
            "version": version,
            "supported": ", ".join(CATALOG["releases"]),
            "location": str(conf.project_root / SDK),
            "status": status,
            "detail": detail,
        }
    )
    report["ready"] = report["ready"] and status == "ready"

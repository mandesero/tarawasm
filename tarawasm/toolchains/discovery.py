from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .catalog import (
    CATALOG,
    TOOLS,
    default_image,
    supported_range,
    tools_for,
    version_status,
)
from .settings import ToolchainError, data_home


def managed_environment() -> dict[str, str]:
    root = data_home()
    paths = [
        root / "bin",
        root / "python/bin",
        root / "node/bin",
        root / "go/bin",
        root / "usr/local/bin",
        root / "opt/wasi-sdk/bin",
        root / "usr/local/lib/tinygo/bin",
        root / "cargo/bin",
    ]
    env = os.environ.copy()
    env["PATH"] = (
        os.pathsep.join(str(path) for path in paths) + os.pathsep + env.get("PATH", "")
    )
    if (root / "rustup").is_dir():
        env.update(RUSTUP_HOME=str(root / "rustup"), CARGO_HOME=str(root / "cargo"))
    if (root / "opt/wasi-sdk").is_dir():
        env["WASI_SDK_PATH"] = str(root / "opt/wasi-sdk")
    return env


def local_environment(profile: dict) -> dict[str, str]:
    env = managed_environment()
    parents = list(
        dict.fromkeys(
            str(Path(path).parent) for path in profile.get("tools", {}).values()
        )
    )
    env["PATH"] = os.pathsep.join([*parents, env["PATH"]])
    clang = profile.get("tools", {}).get("clang")
    if profile.get("tools", {}).get("rustc"):
        env["RUSTC"] = profile["tools"]["rustc"]
    if clang and (Path(clang).parent.parent / "share/wasi-sysroot").is_dir():
        env["WASI_SDK_PATH"] = str(Path(clang).parent.parent)
    return env


@contextmanager
def local_execution_environment(profile: dict):
    env = local_environment(profile)
    node = profile.get("tools", {}).get("node")
    if node:
        # npm and jco use /usr/bin/env node, including when the selected
        # executable has a different basename. Keep the alias operation-local.
        with tempfile.TemporaryDirectory(prefix="tarawasm-node-") as directory:
            (Path(directory) / "node").symlink_to(node)
            env["PATH"] = os.pathsep.join([directory, env["PATH"]])
            yield env
    else:
        yield env


def run_probe(
    argv: list[str], *, env: dict | None = None, timeout: int = 15
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, env=env, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolchainError(f"Cannot inspect {argv[0]}: {exc}") from exc


def discover_local(language: str, profile: dict | None = None) -> dict:
    profile = profile or {"mode": "local"}
    with local_execution_environment(profile) as env:
        return _discover_local(language, profile, env)


def _discover_local(language: str, profile: dict, env: dict[str, str]) -> dict:
    rows = []
    for name in tools_for(language):
        if TOOLS[name]["kind"] == "npm-package":
            package = TOOLS[name]["package"]
            roots = [
                data_home() / "lib/node_modules",
                Path("/usr/lib/node_modules"),
                Path("/usr/local/lib/node_modules"),
            ]
            npm = shutil.which("npm", path=env["PATH"])
            if npm:
                try:
                    result = run_probe([npm, "root", "-g"], env=env)
                    if result.returncode == 0:
                        roots.insert(0, Path(result.stdout.strip()))
                except ToolchainError:
                    pass
            jco = profile.get("tools", {}).get("jco") or shutil.which(
                "jco", path=env["PATH"]
            )
            if jco:
                start = Path(jco).resolve().parent
                if name == "preview2-shim":
                    component = next(
                        (
                            parent / "node_modules/@bytecodealliance/componentize-js"
                            for parent in (start, *start.parents)
                            if (
                                parent
                                / "node_modules/@bytecodealliance/componentize-js/package.json"
                            ).is_file()
                        ),
                        None,
                    )
                    if component:
                        start = component
                roots = [
                    *(parent / "node_modules" for parent in (start, *start.parents)),
                    *roots,
                ]
            row = {
                "tool": name,
                "mode": "local",
                "version": None,
                "supported": supported_range(name),
                "location": None,
                "status": "missing",
                "detail": "package not found",
            }
            for parent in roots:
                metadata = parent / package / "package.json"
                if metadata.is_file():
                    try:
                        version = json.loads(metadata.read_text())["version"]
                        row.update(
                            version=version,
                            location=str(metadata),
                            status=version_status(name, version),
                            detail="found npm package",
                        )
                        if profile.get("versions", {}).get(name) not in (None, version):
                            row.update(
                                status="incompatible",
                                detail="version differs from lock",
                            )
                    except (OSError, ValueError, KeyError):
                        row.update(
                            status="unknown", detail="cannot read package version"
                        )
                    break
            if name == "preview2-shim" and row["status"] == "ready" and jco:
                for parent in Path(jco).resolve().parents:
                    metadata = parent / "package.json"
                    try:
                        is_jco = (
                            metadata.is_file()
                            and json.loads(metadata.read_text()).get("name")
                            == "@bytecodealliance/jco"
                        )
                    except (OSError, ValueError):
                        row.update(
                            status="unknown", detail="cannot read jco package metadata"
                        )
                        break
                    if is_jco:
                        for alias in parent.rglob(
                            "componentize-js-0-19-3/package.json"
                        ):
                            alias_root = alias.parent
                            shim = next(
                                (
                                    directory
                                    / "node_modules"
                                    / package
                                    / "package.json"
                                    for directory in (alias_root, *alias_root.parents)
                                    if (
                                        directory
                                        / "node_modules"
                                        / package
                                        / "package.json"
                                    ).is_file()
                                ),
                                None,
                            )
                            try:
                                alias_version = (
                                    json.loads(shim.read_text())["version"]
                                    if shim
                                    else None
                                )
                                status = (
                                    version_status(name, alias_version)
                                    if alias_version
                                    else "missing"
                                )
                            except (OSError, ValueError, KeyError):
                                status = "unknown"
                            if status != "ready":
                                row.update(
                                    status=status,
                                    detail=f"legacy componentize-js alias shim needs repair: {shim}",
                                )
                                break
                        break
            rows.append(row)
            continue
        path = profile.get("tools", {}).get(name) or shutil.which(
            name, path=env["PATH"]
        )
        row = {
            "tool": name,
            "mode": "local",
            "version": None,
            "supported": supported_range(name),
            "location": path,
            "status": "missing",
            "detail": "not found",
        }
        if path:
            try:
                result = run_probe([path, *TOOLS[name]["version_args"]], env=env)
                raw = result.stdout + result.stderr
                match = re.search(r"(?<![\d.])v?(\d+\.\d+(?:\.\d+)?)(?![\d.\w-])", raw)
                if name == "clang":
                    match = re.search(r"clang version (\d+\.\d+\.\d+)", raw)
                if result.returncode or not match:
                    row.update(
                        status="unknown",
                        detail="version command failed or version cannot be parsed",
                    )
                else:
                    version = match.group(1)
                    if name == "jco":
                        # Some releases retain an older CLI banner. Inspect
                        # metadata belonging to the actual executable.
                        for parent in Path(path).resolve().parents:
                            metadata = parent / "package.json"
                            if metadata.is_file():
                                data = json.loads(metadata.read_text())
                                if data.get("name") == "@bytecodealliance/jco":
                                    version = data["version"]
                                    break
                    row.update(
                        version=version,
                        status=version_status(name, version),
                        detail="found",
                    )
                    if name == "tinygo" and row["status"] == "ready":
                        optimizer = (
                            env.get("WASMOPT")
                            or shutil.which("wasm-opt", path=env["PATH"])
                            or str(Path(path).resolve().with_name("wasm-opt"))
                        )
                        if not os.access(optimizer, os.X_OK):
                            row.update(
                                status="missing", detail="wasm-opt dependency missing"
                            )
                        elif run_probe([optimizer, "--version"], env=env).returncode:
                            row.update(
                                status="incompatible",
                                detail="wasm-opt dependency cannot run",
                            )
                    if name == "clang":
                        sdk = Path(
                            env.get("WASI_SDK_PATH", str(Path(path).parent.parent))
                        )
                        if (
                            not any(
                                target in raw
                                for target in (
                                    "wasm32-unknown-wasi",
                                    "wasm32-unknown-wasip1",
                                )
                            )
                            or not (sdk / "share/wasi-sysroot").is_dir()
                        ):
                            row.update(
                                status="incompatible",
                                detail="WASI SDK compiler/sysroot required",
                            )
                    if name == "rustc" and row["status"] == "ready":
                        target = run_probe(
                            [
                                path,
                                "--print",
                                "target-libdir",
                                "--target",
                                "wasm32-wasip1",
                            ],
                            env=env,
                        )
                        if (
                            target.returncode
                            or not Path(target.stdout.strip()).is_dir()
                        ):
                            row.update(
                                status="incompatible",
                                detail="wasm32-wasip1 target missing",
                            )
                    pinned = profile.get("versions", {}).get(name)
                    if pinned and pinned != version:
                        row.update(
                            status="incompatible", detail=f"lock requires {pinned}"
                        )
            except (ToolchainError, OSError, ValueError, KeyError) as exc:
                row.update(status="unavailable", detail=str(exc))
        rows.append(row)
    return {
        "language": language,
        "mode": "local",
        "tools": rows,
        "ready": all(row["status"] == "ready" for row in rows),
    }


def docker_available() -> tuple[bool, str]:
    if not shutil.which("docker"):
        return False, "Docker CLI missing; install Docker for your platform first."
    try:
        result = run_probe(["docker", "info", "--format", "{{.ServerVersion}}"])
    except ToolchainError as exc:
        return False, str(exc)
    return result.returncode == 0, (
        result.stderr.strip() if result.returncode else result.stdout.strip()
    )


def docker_prefix(profile: dict) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--pull=never",
        "--platform",
        profile.get("platform", CATALOG["docker_platform"]),
    ]


def discover_docker(language: str, profile: dict) -> dict:
    image = profile.get("image", default_image(language))
    report: dict = {
        "language": language,
        "mode": "docker",
        "image": image,
        "platform": profile.get("platform", CATALOG["docker_platform"]),
        "ready": False,
        "tools": [],
    }
    available, detail = docker_available()
    if not available:
        return {**report, "status": "unavailable", "detail": detail}
    inspected = run_probe(["docker", "image", "inspect", image])
    if inspected.returncode:
        return {
            **report,
            "status": "not downloaded",
            "detail": f"Run: tarawasm toolchain setup {language} --mode docker --image {image} --install",
        }
    metadata = json.loads(inspected.stdout)[0]
    report["image_id"] = metadata["Id"]
    report["digests"] = metadata.get("RepoDigests", [])
    result = run_probe(
        [
            *docker_prefix(profile),
            "--network=none",
            "--entrypoint",
            "python3",
            image,
            "-m",
            "tarawasm.cli",
            "doctor",
            "--lang",
            language,
            "--json",
        ],
        timeout=90,
    )
    try:
        inside = json.loads(result.stdout)
        rows = inside["reports"][0]["tools"]
        if not isinstance(rows, list) or {row["tool"] for row in rows} != set(
            tools_for(language)
        ):
            raise ValueError("unexpected tool inventory")
        for row in rows:
            row["mode"] = "docker"
            name, version = row["tool"], row.get("version")
            if version and version_status(name, version) != "ready":
                row["status"] = version_status(name, version)
            if profile.get("versions", {}).get(name) not in (None, version):
                row.update(status="incompatible", detail="version differs from lock")
        report.update(
            tools=rows,
            ready=result.returncode == 0
            and all(row["status"] == "ready" for row in rows),
            status="checked",
        )
    except (ValueError, KeyError, TypeError) as exc:
        report.update(
            status="unknown",
            detail=f"Image must provide tarawasm doctor: {exc}; {result.stderr.strip()}",
        )
    return report


def inspect_profile(language: str, profile: dict | None) -> dict:
    if profile and profile["mode"] == "docker":
        return discover_docker(language, profile)
    return discover_local(language, profile)

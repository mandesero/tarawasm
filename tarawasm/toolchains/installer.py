from __future__ import annotations

import hashlib
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from .catalog import CATALOG, TOOLS, version_tuple
from .discovery import discover_local, managed_environment
from .settings import ToolchainError, data_home

MACOS_CHECKSUMS = {
    "tinygo": {
        "arm64": "493da3585e66c5da677a4be39402faf2041b4e45a61eb456e4547eca753a544e",
        "amd64": "ef7b96cf59de5714a7493a696e9db141a85a99459620b00c42cb3bad14be2af2",
    },
    "wasi-sdk": {
        "arm64": "9c59398106b417f8f14913380fdf0097a8cc0ff4af9eb3ce0065a859e88d49e9",
        "amd64": "87d27fa8adc68dee59bfbf2e22a6d34ef717c34d6bf1d8af2a56fc929d9ce0eb",
    },
    "wasm-tools": {
        "arm64": "94c4fc9baeada6e793f0d4adeca537633b5d93e9dc6bf718be2f478f4afe0296",
        "amd64": "354a84ffeede30ba11f29bc72de76875a977cf43bf1c5bdc3e91e2313e8a854b",
    },
    "wkg": {
        "arm64": "3ad0e1d2698607bffe4900fd2320f7d359ec672d8c8a359c77ae4c5e0c7fb3b7",
        "amd64": "ce1ea6f3aab7756009c523ff68bc973dc4479c744f227a7f087df284143fbe2d",
    },
    "wit-bindgen": {
        "arm64": "68a8898f8d139d24bd129c5206007dfb7636898edf7659348760d8159ecea9d6",
        "amd64": "0fe161319d31be62e2a39c8786772230a36e120be457d67c34b67706de91911b",
    },
    "go": {
        "arm64": "ee215d57e0ec269c60cc9ceca68e6bda321ba9ee5afe24f4b0988703c2d87d12",
        "amd64": "8f8f52c6649542cf027bbc9b9c68d1ec042f9f34808a40413f0b8b3f66f3caa4",
    },
    "binaryen": {
        "arm64": "d8c978aec366629eae6fefbcedaf5093b829e4c5ab0e2990973b6e337c544867",
        "amd64": "266f63d3d8d9e17d5e532b8fc6c5340f92b3fea2020a634957a6dd938294ba56",
    },
}

LINUX_CHECKSUMS = {
    "tinygo": "b87688fa2e19cee7d813cad7fd7dadb71dff3198e47125aba66ba4af5e490438",
    "wasi-sdk": "b761e3a0721dbae9c09a0059e5fdb2bf917d1b4a8a7b430fb3b5aafb0984b2c4",
    "go": "63d339f0da5ab53635a56f2490a7984dfe12dfcff22ad749f63edaf590168445",
}


def host_architecture() -> str:
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    if machine in {"x86_64", "amd64"}:
        return "amd64"
    raise ToolchainError(f"Unsupported local installation architecture: {machine}")


def linux_package_manager() -> str:
    release = Path("/etc/os-release")
    if not release.is_file():
        raise ToolchainError(
            "Cannot identify Linux distribution: /etc/os-release missing."
        )
    values = {}
    for line in release.read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {"ID", "ID_LIKE"}:
            try:
                values[key] = " ".join(shlex.split(value)).lower()
            except ValueError as exc:
                raise ToolchainError("Invalid /etc/os-release.") from exc
    families = {values.get("ID", ""), *values.get("ID_LIKE", "").split()}
    if families & {"ubuntu", "debian", "astra", "astra_linux"}:
        candidates: tuple[str, ...] = ("apt-get",)
    elif families & {"fedora", "rhel", "centos", "redos"}:
        candidates = ("dnf", "yum")
    else:
        raise ToolchainError(
            "Automatic Linux installation supports Debian/Ubuntu/Astra and Fedora/CentOS/RED OS families. Use Docker or supply local tools with toolchain set."
        )
    for candidate in candidates:
        if shutil.which(candidate):
            return candidate
    raise ToolchainError(
        f"Required package manager missing: {' or '.join(candidates)}."
    )


def supported_host() -> None:
    if platform.system() == "Darwin":
        host_architecture()
        return
    if platform.system() != "Linux" or host_architecture() != "amd64":
        raise ToolchainError(
            "Automatic local installation supports macOS arm64/x86-64 and glibc Linux x86-64. Use Docker or supply local tools with toolchain set."
        )
    linux_package_manager()
    libc, version = platform.libc_ver()
    if (
        libc != "glibc"
        or not version
        or tuple(int(x) for x in version.split(".")[:2]) < (2, 28)
    ):
        raise ToolchainError(
            "Managed Linux releases require glibc 2.28+. Use Docker on older or musl systems."
        )


def missing_prerequisites() -> list[str]:
    if platform.system() == "Darwin":
        missing = [name for name in ("python3", "cc", "git") if not shutil.which(name)]
        try:
            result = subprocess.run(
                ["xcrun", "--find", "clang"],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            if result.returncode:
                missing.append("Xcode Command Line Tools")
        except (OSError, subprocess.TimeoutExpired):
            missing.append("Xcode Command Line Tools")
        return missing
    return [
        name
        for name in ("python3", "cc", "pkg-config", "git")
        if not shutil.which(name)
    ]


def installation_plan(
    languages: list[str],
    *,
    upgrade: bool = False,
    profiles: dict[str, dict] | None = None,
) -> list[str]:
    supported_host()
    profiles = profiles or {}
    reports = [
        discover_local(language, profiles.get(language)) for language in languages
    ]
    all_rows = [row for report in reports for row in report["tools"]]
    requested = {
        row["tool"]
        for language, report in zip(languages, reports)
        for row in report["tools"]
        if row["status"] != "ready"
        or (
            upgrade
            and TOOLS[row["tool"]]["kind"] != "system"
            and row.get("version")
            and version_tuple(row["version"])
            < version_tuple(TOOLS[row["tool"]]["recommended"])
            and row["tool"] not in profiles.get(language, {}).get("versions", {})
            and row["tool"] not in profiles.get(language, {}).get("tools", {})
        )
    }
    replacing_rust = any(TOOLS[name]["kind"] == "rust" for name in requested)
    blocked = [
        row["tool"] for row in all_rows if row["status"] not in {"ready", "missing"}
    ]
    if blocked and not upgrade:
        raise ToolchainError(
            f"Existing tools need attention: {', '.join(blocked)}. Inspect doctor, or pass --upgrade to install managed replacements."
        )
    replacing_npm = any(
        TOOLS[name]["kind"] in {"npm", "npm-package"} for name in requested
    )
    for language, report in zip(languages, reports):
        rows = {row["tool"]: row for row in report["tools"]}
        profile = profiles.get(language, {})
        for name, version in profile.get("versions", {}).items():
            if (
                name in requested
                or (replacing_npm and TOOLS[name]["kind"] in {"npm", "npm-package"})
                or (replacing_rust and TOOLS[name]["kind"] == "rust")
            ) and version != TOOLS[name]["recommended"]:
                raise ToolchainError(
                    f"Locked {name} {version} is not available from the managed installer. Provide this version manually or use its locked Docker image."
                )
        for name, path in profile.get("tools", {}).items():
            if replacing_npm and TOOLS[name]["kind"] in {"npm", "npm-package"}:
                raise ToolchainError(
                    f"Selected npm tool {name} at {path} must be prepared separately; setup cannot change an explicit npm selection."
                )
            if replacing_rust and TOOLS[name]["kind"] == "rust":
                raise ToolchainError(
                    f"Selected Rust binary {name} at {path} must be prepared separately; setup cannot change an explicit Rust selection."
                )
            if rows[name]["status"] != "ready":
                raise ToolchainError(
                    f"Selected binary {name} at {path} needs repair. The installer will not replace an explicit custom path."
                )
    return list(
        dict.fromkeys(row["tool"] for row in all_rows if row["tool"] in requested)
    )


def download(url: str, destination: Path, checksum: str | None = None) -> None:
    with (
        urllib.request.urlopen(url, timeout=60) as response,
        destination.open("wb") as stream,
    ):
        shutil.copyfileobj(response, stream)
    if checksum and hashlib.sha256(destination.read_bytes()).hexdigest() != checksum:
        destination.unlink()
        raise ToolchainError(f"SHA256 mismatch for {url}")


def extract_archive(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            if Path(member.name).is_absolute() or ".." in Path(member.name).parts:
                raise ToolchainError("Unsafe archive member.")
            target = (root / member.name).resolve()
            if not target.is_relative_to(root) or member.isdev() or member.isfifo():
                raise ToolchainError("Unsafe archive member.")
            if member.issym() or member.islnk():
                link = (target.parent if member.issym() else root) / member.linkname
                if not link.resolve().is_relative_to(root):
                    raise ToolchainError("Unsafe archive link.")
            # Re-evaluate each path after earlier links have been extracted.
            # This validation also works on supported Python 3.10.
            if hasattr(tarfile, "data_filter"):
                source.extract(member, destination, filter="data")
            else:
                source.extract(member, destination)


def execute(argv: list[str], env: dict[str, str]) -> None:
    try:
        subprocess.run(argv, env=env, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ToolchainError(f"Installation failed: {argv[0]}: {exc}") from exc


def copy_release_file(source, destination):
    # Replacing the inode avoids stale macOS executable signature caches after
    # upgrades. Copying over an existing signed Mach-O can make it unlaunchable.
    destination = Path(destination)
    descriptor, staged = tempfile.mkstemp(prefix=".release-", dir=destination.parent)
    os.close(descriptor)
    try:
        if Path(source).is_symlink():
            Path(staged).unlink()
            os.symlink(os.readlink(source), staged)
        else:
            shutil.copy2(source, staged)
        os.replace(staged, destination)
    finally:
        Path(staged).unlink(missing_ok=True)
    return str(destination)


def copy_release_tree(source: Path, destination: Path) -> None:
    if destination.is_symlink():
        raise ToolchainError(f"Release directory must not be a symlink: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        target = destination / entry.name
        if entry.is_symlink() or not entry.is_dir():
            copy_release_file(entry, target)
        else:
            copy_release_tree(entry, target)


def replace_release_tree(source: Path, destination: Path) -> None:
    """Stage a complete release, then replace it without retaining obsolete files."""
    if destination.is_symlink():
        raise ToolchainError(f"Release directory must not be a symlink: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".release-", dir=destination.parent))
    staged = work / "new"
    backup = work / "previous"
    published = False
    try:
        copy_release_tree(source, staged)
        if destination.exists():
            destination.rename(backup)
        staged.rename(destination)
        published = True
    except BaseException:
        if backup.exists():
            try:
                backup.rename(destination)
            except OSError as exc:
                raise ToolchainError(
                    f"Release restoration failed; recover the previous release from {backup}: {exc}"
                ) from exc
        raise
    finally:
        # Never remove the only recoverable old release after failed restoration.
        if published or not backup.exists():
            shutil.rmtree(work)


def bootstrap_rust(root: Path, env: dict[str, str], temporary: Path) -> None:
    env.update(CARGO_HOME=str(root / "cargo"), RUSTUP_HOME=str(root / "rustup"))
    env["PATH"] = str(root / "cargo/bin") + os.pathsep + env["PATH"]
    rustup = root / "cargo/bin/rustup"
    if not rustup.is_file():
        script = temporary / "rustup.sh"
        download("https://sh.rustup.rs", script)
        execute(
            [
                "sh",
                str(script),
                "-y",
                "--no-modify-path",
                "--profile",
                "minimal",
                "--default-toolchain",
                TOOLS["rustc"]["recommended"],
            ],
            env,
        )
    execute(
        [
            str(rustup),
            "toolchain",
            "install",
            TOOLS["rustc"]["recommended"],
            "--profile",
            "minimal",
        ],
        env,
    )
    execute([str(rustup), "default", TOOLS["rustc"]["recommended"]], env)
    execute([str(rustup), "target", "add", "wasm32-wasip1"], env)


def install_tools(names: list[str]) -> None:
    supported_host()
    root = data_home()
    root.mkdir(parents=True, exist_ok=True)
    env = managed_environment()
    macos = platform.system() == "Darwin"
    architecture = host_architecture()
    if macos and any(
        TOOLS[name]["kind"] == "cargo" and name not in MACOS_CHECKSUMS for name in names
    ):
        try:
            openssl = subprocess.check_output(
                ["brew", "--prefix", "openssl@3"], env=env, text=True
            ).strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ToolchainError(
                "Prepare Homebrew openssl@3 before compiling cargo tools."
            ) from exc
        env["PKG_CONFIG_PATH"] = os.pathsep.join(
            filter(
                None, [str(Path(openssl) / "lib/pkgconfig"), env.get("PKG_CONFIG_PATH")]
            )
        )
    with tempfile.TemporaryDirectory(prefix="tarawasm-install-") as rendered:
        temporary = Path(rendered)
        # A compiler used only to build cargo-installed tools must not shadow
        # an already ready host Rust toolchain (including its pinned version).
        rust_root = (
            root
            if any(TOOLS[name]["kind"] == "rust" for name in names)
            else root / "bootstrap"
        )
        if any(
            TOOLS[name]["kind"] in {"cargo", "rust"}
            and not (macos and name in MACOS_CHECKSUMS)
            for name in names
        ):
            bootstrap_rust(rust_root, env, temporary)
        npm_installed = False
        for name in names:
            spec = TOOLS[name]
            version, kind = (
                spec.get("install_version", spec["recommended"]),
                spec["kind"],
            )
            if kind == "system":
                raise ToolchainError(
                    "Python 3.10+ must be installed by the system administrator."
                )
            if kind == "cargo":
                if macos and name in MACOS_CHECKSUMS:
                    install_macos_binary(name, version, architecture, root, temporary)
                    continue
                execute(
                    [
                        str(rust_root / "cargo/bin/cargo"),
                        "install",
                        "--locked",
                        "--root",
                        str(root),
                        spec["package"],
                        "--version",
                        version,
                        "--force",
                    ],
                    env,
                )
            elif kind == "rust":
                # bootstrap_rust prepared both compiler and WASI target.
                continue
            elif kind == "pip":
                python = root / "python/bin/python3"
                if not python.is_file():
                    execute([sys.executable, "-m", "venv", str(root / "python")], env)
                execute(
                    [
                        str(python),
                        "-m",
                        "pip",
                        "install",
                        f"{spec['package']}=={version}",
                    ],
                    env,
                )
            elif kind == "go":
                archive = temporary / "go.tar.gz"
                download(
                    f"https://go.dev/dl/go{version}.{'darwin' if macos else 'linux'}-{architecture}.tar.gz",
                    archive,
                    (
                        MACOS_CHECKSUMS["go"][architecture]
                        if macos
                        else LINUX_CHECKSUMS["go"]
                    ),
                )
                extract_archive(archive, temporary / "go-extracted")
                replace_release_tree(temporary / "go-extracted/go", root / "go")
            elif kind == "node":
                archive = temporary / "node.tar.gz"
                base = f"https://nodejs.org/dist/v{version}"
                sums = temporary / "node-sums.txt"
                download(f"{base}/SHASUMS256.txt", sums)
                node_platform = f"{'darwin' if macos else 'linux'}-{'x64' if architecture == 'amd64' else 'arm64'}"
                filename = f"node-v{version}-{node_platform}.tar.gz"
                checksum = next(
                    line.split()[0]
                    for line in sums.read_text().splitlines()
                    if line.split()[-1] == filename
                )
                download(f"{base}/{filename}", archive, checksum)
                extract_archive(archive, temporary)
                replace_release_tree(
                    temporary / f"node-v{version}-{node_platform}",
                    root / "node",
                )
            elif kind in {"npm", "npm-package"}:
                if npm_installed:
                    continue
                npm_installed = True
                npm = shutil.which("npm", path=env["PATH"])
                if not npm:
                    raise ToolchainError(
                        "npm missing; install the Node toolchain first."
                    )
                packages = [
                    f"{TOOLS['jco']['package']}@{TOOLS['jco']['recommended']}",
                    f"@bytecodealliance/componentize-js@{CATALOG['packages']['componentize-js']}",
                    f"@bytecodealliance/preview2-shim@{CATALOG['packages']['preview2-shim']}",
                ]
                execute(
                    [npm, "install", "--global", "--prefix", str(root), *packages], env
                )
                # The embedding splicer imports this dependency from its own
                # package. Pin that resolution too, not just the global sibling.
                component_roots = [
                    root / "lib/node_modules/@bytecodealliance/componentize-js"
                ]
                nested = (
                    root
                    / "lib/node_modules/@bytecodealliance/jco/node_modules/@bytecodealliance/componentize-js"
                )
                if nested.is_dir():
                    component_roots.append(nested)
                # jco carries a 0.19.3 alias for older WASI HTTP worlds. Its
                # splicer needs the same compatible filesystem shim.
                component_roots.extend(
                    metadata.parent
                    for metadata in (root / "lib/node_modules").rglob(
                        "componentize-js*/package.json"
                    )
                    if json.loads(metadata.read_text()).get("name")
                    == "@bytecodealliance/componentize-js"
                )
                for component_root in dict.fromkeys(component_roots):
                    execute(
                        [
                            npm,
                            "install",
                            "--prefix",
                            str(component_root),
                            "--save-prod",
                            "--save-exact",
                            "--omit=dev",
                            "--package-lock=false",
                            "--ignore-scripts",
                            f"@bytecodealliance/preview2-shim@{CATALOG['packages']['preview2-shim']}",
                        ],
                        env,
                    )
            elif kind in {"tinygo", "wasi-sdk"}:
                if macos:
                    install_macos_sdk(kind, version, architecture, root, temporary)
                    if kind == "wasi-sdk":
                        env["WASI_SDK_PATH"] = str(root / "opt/wasi-sdk")
                    continue
                install_linux_sdk(kind, version, root, temporary)
                if kind == "wasi-sdk":
                    env["WASI_SDK_PATH"] = str(root / "opt/wasi-sdk")


def install_linux_sdk(kind: str, version: str, root: Path, temporary: Path) -> None:
    if kind == "tinygo":
        folder = "tinygo"
        url = f"https://github.com/tinygo-org/tinygo/releases/download/v{version}/tinygo{version}.linux-amd64.tar.gz"
        destination = root / "usr/local/lib/tinygo"
    else:
        folder = f"wasi-sdk-{version}-x86_64-linux"
        url = f"https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-{version.split('.')[0]}/{folder}.tar.gz"
        destination = root / "opt/wasi-sdk"
    archive = temporary / f"{kind}.tar.gz"
    download(url, archive, LINUX_CHECKSUMS[kind])
    extracted = temporary / f"{kind}-extracted"
    extract_archive(archive, extracted)
    replace_release_tree(extracted / folder, destination)


def install_macos_binary(
    name: str, version: str, architecture: str, root: Path, temporary: Path
) -> None:
    arch = "aarch64" if architecture == "arm64" else "x86_64"
    if name == "wkg":
        url = f"https://github.com/bytecodealliance/wasm-pkg-tools/releases/download/v{version}/wkg-{arch}-apple-darwin"
    else:
        url = f"https://github.com/bytecodealliance/{name}/releases/download/v{version}/{name}-{version}-{arch}-macos.tar.gz"
    downloaded = temporary / f"{name}-download"
    download(url, downloaded, MACOS_CHECKSUMS[name][architecture])
    if name == "wkg":
        binary = downloaded
    else:
        extracted = temporary / name
        extract_archive(downloaded, extracted)
        candidates = [path for path in extracted.rglob(name) if path.is_file()]
        if len(candidates) != 1:
            raise ToolchainError(f"Expected one {name} executable in release archive.")
        binary = candidates[0]
    (root / "bin").mkdir(parents=True, exist_ok=True)
    copy_release_file(binary, root / "bin" / name)
    (root / "bin" / name).chmod(0o755)


def install_macos_sdk(
    kind: str, version: str, architecture: str, root: Path, temporary: Path
) -> None:
    if kind == "tinygo":
        url = f"https://github.com/tinygo-org/tinygo/releases/download/v{version}/tinygo{version}.darwin-{architecture}.tar.gz"
        folder = "tinygo"
        destination = root / "usr/local/lib/tinygo"
    else:
        arch = "arm64" if architecture == "arm64" else "x86_64"
        folder = f"wasi-sdk-{version}-{arch}-macos"
        url = f"https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-{version.split('.')[0]}/{folder}.tar.gz"
        destination = root / "opt/wasi-sdk"
    archive = temporary / f"{kind}.tar.gz"
    download(url, archive, MACOS_CHECKSUMS[kind][architecture])
    extracted = temporary / f"{kind}-extracted"
    extract_archive(archive, extracted)
    if kind == "tinygo":
        # TinyGo bundles Binaryen 116 on Linux, but omits it on macOS.
        arch = "arm64" if architecture == "arm64" else "x86_64"
        binaryen = temporary / "binaryen.tar.gz"
        download(
            f"https://github.com/WebAssembly/binaryen/releases/download/version_116/binaryen-version_116-{arch}-macos.tar.gz",
            binaryen,
            MACOS_CHECKSUMS["binaryen"][architecture],
        )
        extract_archive(binaryen, temporary / "binaryen")
        copy_release_tree(
            temporary / "binaryen/binaryen-version_116", extracted / folder
        )
    replace_release_tree(extracted / folder, destination)


def prerequisites_command() -> list[str]:
    if platform.system() == "Darwin":
        return ["brew", "install", "pkg-config", "openssl@3"]
    manager = linux_package_manager()
    packages = (
        [
            "build-essential",
            "pkg-config",
            "libssl-dev",
            "python3-venv",
            "python3-dev",
            "ca-certificates",
            "curl",
            "git",
        ]
        if manager == "apt-get"
        else [
            "gcc",
            "gcc-c++",
            "make",
            "pkgconf-pkg-config" if manager == "dnf" else "pkgconfig",
            "openssl-devel",
            "python3-devel",
            "ca-certificates",
            "curl",
            "git",
        ]
    )
    return ([] if os.getuid() == 0 else ["sudo"]) + [
        manager,
        "install",
        "-y",
        *packages,
    ]


def prerequisite_commands(names: list[str]) -> list[list[str]]:
    if platform.system() != "Darwin":
        install = prerequisites_command()
        manager = linux_package_manager()
        return (
            [install[: install.index(manager) + 1] + ["update"], install]
            if manager == "apt-get"
            else [install]
        )
    if missing_prerequisites():
        raise ToolchainError(
            "Python 3.10+ and Xcode Command Line Tools are required. Run xcode-select --install, then retry."
        )
    if any(
        TOOLS[name]["kind"] == "cargo" and name not in MACOS_CHECKSUMS for name in names
    ):
        if not shutil.which("brew"):
            raise ToolchainError(
                "Homebrew is required to prepare cargo build dependencies. Install Homebrew, then retry."
            )
        return [prerequisites_command()]
    return []


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Install managed, pinned tarawasm tools on macOS or supported glibc Linux x86-64."
    )
    parser.add_argument("tools", nargs="+", choices=list(TOOLS))
    args = parser.parse_args()
    try:
        install_tools(args.tools)
    except (ToolchainError, OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()

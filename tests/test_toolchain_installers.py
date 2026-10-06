import io
import tarfile

import pytest

from tarawasm.toolchains import installer
from tarawasm.toolchains.catalog import tools_for
from tarawasm.toolchains.settings import ToolchainError


@pytest.fixture
def macos(tmp_path, monkeypatch):
    monkeypatch.setenv("TARAWASM_DATA_HOME", str(tmp_path / "tools"))
    monkeypatch.setattr(installer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(installer.platform, "machine", lambda: "arm64")
    return tmp_path


@pytest.mark.parametrize(
    "machine,architecture", [("arm64", "arm64"), ("x86_64", "amd64")]
)
def test_macos_release_archives_populate_runtime_paths(
    macos, monkeypatch, machine, architecture
):
    monkeypatch.setattr(installer.platform, "machine", lambda: machine)
    downloads = []

    def download(url, destination, checksum=None):
        downloads.append((url, checksum))
        assert checksum and len(checksum) == 64
        if "go1.27.1" in url:
            name = "go/bin/go"
        elif "tinygo0.42.0" in url:
            name = "tinygo/bin/tinygo"
        elif "binaryen" in url:
            name = "binaryen-version_116/bin/wasm-opt"
        else:
            sdk_arch = "arm64" if architecture == "arm64" else "x86_64"
            name = f"wasi-sdk-34.0-{sdk_arch}-macos/bin/clang"
        with tarfile.open(destination, "w:gz") as archive:
            member = tarfile.TarInfo(name)
            member.size = 4
            member.mode = 0o755
            archive.addfile(member, io.BytesIO(b"tool"))

    monkeypatch.setattr(installer, "download", download)
    monkeypatch.setattr(
        installer, "bootstrap_rust", lambda *_: pytest.fail("unexpected Rust bootstrap")
    )
    installer.install_tools(["go", "tinygo", "clang"])
    root = macos / "tools"
    for name in (
        "go/bin/go",
        "usr/local/lib/tinygo/bin/tinygo",
        "usr/local/lib/tinygo/bin/wasm-opt",
        "opt/wasi-sdk/bin/clang",
    ):
        assert (root / name).read_bytes() == b"tool"
    assert f"darwin-{architecture}" in downloads[0][0]
    assert f"darwin-{architecture}" in downloads[1][0]
    assert downloads[2][1] == installer.MACOS_CHECKSUMS["binaryen"][architecture]
    assert downloads[3][1] == installer.MACOS_CHECKSUMS["wasi-sdk"][architecture]


def test_macos_prebuilt_wkg_does_not_bootstrap_rust(macos, monkeypatch):
    def download(url, destination, checksum=None):
        assert url.endswith("wkg-aarch64-apple-darwin")
        assert checksum == installer.MACOS_CHECKSUMS["wkg"]["arm64"]
        destination.write_bytes(b"binary")

    monkeypatch.setattr(installer, "download", download)
    monkeypatch.setattr(
        installer, "bootstrap_rust", lambda *_: pytest.fail("unexpected Rust bootstrap")
    )
    installer.install_tools(["wkg"])
    assert (macos / "tools/bin/wkg").stat().st_mode & 0o111


def test_macos_archive_tools_do_not_require_homebrew(macos, monkeypatch):
    monkeypatch.setattr(installer, "missing_prerequisites", list)
    monkeypatch.setattr(installer.shutil, "which", lambda _name: None)
    assert installer.prerequisite_commands(["go", "wkg", "clang"]) == []
    with pytest.raises(ToolchainError, match="Homebrew"):
        installer.prerequisite_commands(["cargo-component"])


def test_macos_missing_prerequisites_fail_before_install(macos, monkeypatch):
    monkeypatch.setattr(installer, "missing_prerequisites", lambda: ["cc"])
    with pytest.raises(ToolchainError, match="xcode-select --install"):
        installer.prerequisite_commands(["go"])
    assert not (macos / "tools").exists()


def test_download_checksum_mismatch_removes_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(
        installer.urllib.request, "urlopen", lambda *_a, **_k: io.BytesIO(b"incorrect")
    )
    destination = tmp_path / "archive"
    with pytest.raises(ToolchainError, match="SHA256 mismatch"):
        installer.download("https://example.test/archive", destination, "0" * 64)
    assert not destination.exists()


def test_cargo_plugin_bootstrap_preserves_active_rust(macos, monkeypatch):
    root = macos / "tools"
    monkeypatch.setenv("RUSTUP_HOME", "/existing/rustup")
    monkeypatch.setenv("CARGO_HOME", "/existing/cargo")
    monkeypatch.setattr(
        installer.subprocess, "check_output", lambda *_a, **_kw: "/openssl\n"
    )
    bootstraps = []
    commands = []

    def bootstrap(compiler_root, env, _temporary):
        bootstraps.append(compiler_root)
        (compiler_root / "rustup").mkdir(parents=True)
        env.update(
            RUSTUP_HOME=str(compiler_root / "rustup"),
            CARGO_HOME=str(compiler_root / "cargo"),
        )

    monkeypatch.setattr(installer, "bootstrap_rust", bootstrap)
    monkeypatch.setattr(
        installer, "execute", lambda argv, env: commands.append((argv, env.copy()))
    )
    installer.install_tools(["cargo-component"])
    assert bootstraps == [root / "bootstrap"]
    assert commands[0][0][0] == str(root / "bootstrap/cargo/bin/cargo")
    assert "--root" in commands[0][0] and str(root) in commands[0][0]
    assert not (root / "rustup").exists()
    assert installer.managed_environment()["RUSTUP_HOME"] == "/existing/rustup"


def test_managed_rust_bootstrap_always_installs_wasi_target(macos, monkeypatch):
    commands = []
    monkeypatch.setattr(
        installer, "download", lambda _url, path: path.write_text("installer")
    )
    monkeypatch.setattr(installer, "execute", lambda argv, _env: commands.append(argv))
    installer.bootstrap_rust(macos / "tools", {"PATH": "/usr/bin"}, macos)
    assert commands[-1][-3:] == ["target", "add", "wasm32-wasip1"]


def test_rust_replacement_preserves_ready_sibling_constraints(macos, monkeypatch):
    report = {
        "tools": [
            {"tool": name, "status": "incompatible" if name == "rustc" else "ready"}
            for name in tools_for("rust")
        ]
    }
    monkeypatch.setattr(installer, "discover_local", lambda *_: report)
    with pytest.raises(ToolchainError, match="Locked cargo 1.96.0"):
        installer.installation_plan(
            ["rust"], upgrade=True, profiles={"rust": {"versions": {"cargo": "1.96.0"}}}
        )
    with pytest.raises(ToolchainError, match="explicit Rust selection"):
        installer.installation_plan(
            ["rust"],
            upgrade=True,
            profiles={"rust": {"tools": {"cargo": "/existing/cargo"}}},
        )
    assert not (macos / "tools").exists()


def test_macos_compiler_stub_is_not_a_ready_prerequisite(macos, monkeypatch):
    monkeypatch.setattr(installer.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(
        installer.subprocess,
        "run",
        lambda *_a, **_kw: type("Result", (), {"returncode": 1})(),
    )
    assert "Xcode Command Line Tools" in installer.missing_prerequisites()


def test_npm_install_pins_splicer_dependency(macos, monkeypatch):
    commands = []
    monkeypatch.setattr(installer.shutil, "which", lambda *_a, **_k: "/npm")
    monkeypatch.setattr(installer, "execute", lambda argv, env: commands.append(argv))
    root = macos / "tools"
    nested = (
        root
        / "lib/node_modules/@bytecodealliance/jco/node_modules/@bytecodealliance/componentize-js"
    )
    nested.mkdir(parents=True)
    installer.install_tools(["jco"])
    assert len(commands) == 3
    assert commands[1][commands[1].index("--prefix") + 1] == str(
        root / "lib/node_modules/@bytecodealliance/componentize-js"
    )
    assert commands[2][commands[2].index("--prefix") + 1] == str(nested)
    assert commands[2][-1] == "@bytecodealliance/preview2-shim@0.17.8"
    assert "--save-prod" in commands[2] and "--omit=dev" in commands[2]


def test_release_copy_replaces_inode_and_preserves_old_file_on_failure(
    tmp_path, monkeypatch
):
    source = tmp_path / "source"
    destination = tmp_path / "binary"
    source.write_bytes(b"new")
    source.chmod(0o755)
    destination.write_bytes(b"old")
    old = destination.stat().st_ino
    installer.copy_release_file(source, destination)
    assert destination.read_bytes() == b"new"
    assert destination.stat().st_ino != old
    assert destination.stat().st_mode & 0o111

    def fail(*_args, **_kwargs):
        raise OSError("copy failed")

    monkeypatch.setattr(installer.shutil, "copy2", fail)
    with pytest.raises(OSError, match="copy failed"):
        installer.copy_release_file(source, destination)
    assert destination.read_bytes() == b"new"
    assert not list(tmp_path.glob(".release-*"))


def test_release_tree_preserves_links_on_reinstall(tmp_path):
    source = tmp_path / "release"
    (source / "bin").mkdir(parents=True)
    (source / "lib").mkdir()
    (source / "lib/cli.js").write_text("relative imports")
    (source / "bin/npm").symlink_to("../lib/cli.js")
    destination = tmp_path / "installed"
    for _ in range(2):
        installer.copy_release_tree(source, destination)
        assert (destination / "bin/npm").is_symlink()
        assert (destination / "bin/npm").read_text() == "relative imports"
    (destination / "lib").rename(tmp_path / "original-lib")
    (destination / "lib").symlink_to(
        tmp_path / "original-lib", target_is_directory=True
    )
    with pytest.raises(ToolchainError, match="must not be a symlink"):
        installer.copy_release_tree(source, destination)


@pytest.fixture
def linux(tmp_path, monkeypatch):
    from pathlib import Path

    release = tmp_path / "os-release"
    release.write_text('ID=debian\nVERSION_ID="12"\n')
    monkeypatch.setattr(
        installer,
        "Path",
        lambda value: release if value == "/etc/os-release" else Path(value),
    )
    monkeypatch.setattr(installer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(installer.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(installer.platform, "libc_ver", lambda: ("glibc", "2.28"))
    monkeypatch.setenv("TARAWASM_DATA_HOME", str(tmp_path / "tools"))
    return release


@pytest.mark.parametrize(
    "release,available,manager",
    [
        ("ID=ubuntu", ["apt-get"], "apt-get"),
        ('ID=debian\nVERSION_ID="12"', ["apt-get"], "apt-get"),
        ("ID=astra\nID_LIKE=debian", ["apt-get"], "apt-get"),
        ("ID=fedora", ["dnf", "yum"], "dnf"),
        ('ID=centos\nID_LIKE="rhel fedora"', ["dnf"], "dnf"),
        ('ID=redos\nID_LIKE="rhel fedora"', ["yum"], "yum"),
        ('ID=rocky\nID_LIKE="rhel centos fedora"', ["dnf"], "dnf"),
    ],
)
def test_linux_selects_distribution_package_manager(
    linux, monkeypatch, release, available, manager
):
    linux.write_text(release)
    monkeypatch.setattr(
        installer.shutil,
        "which",
        lambda name: "/bin/" + name if name in available else None,
    )
    monkeypatch.setattr(installer.os, "getuid", lambda: 0)
    installer.supported_host()
    commands = installer.prerequisite_commands(["wasm-tools"])
    assert all(command[0] == manager for command in commands)
    assert commands[-1][1:3] == ["install", "-y"]
    if manager == "apt-get":
        assert commands[0] == ["apt-get", "update"]
        assert "libssl-dev" in commands[-1]
    else:
        assert len(commands) == 1 and "openssl-devel" in commands[0]
        assert "gcc-c++" in commands[0]
    monkeypatch.setattr(installer.os, "getuid", lambda: 1000)
    assert installer.prerequisites_command()[:2] == ["sudo", manager]


@pytest.mark.parametrize("libc,version", [("musl", "1.2"), ("glibc", "2.27"), ("", "")])
def test_linux_rejects_incompatible_libc_before_writing(
    linux, monkeypatch, libc, version
):
    monkeypatch.setattr(installer.shutil, "which", lambda name: "/bin/" + name)
    monkeypatch.setattr(installer.platform, "libc_ver", lambda: (libc, version))
    with pytest.raises(ToolchainError, match="glibc 2.28"):
        installer.install_tools(["tinygo"])
    assert not (linux.parent / "tools").exists()


def test_linux_rejects_unknown_distribution_or_missing_manager(linux, monkeypatch):
    linux.write_text("ID=alpine")
    with pytest.raises(ToolchainError, match="families"):
        installer.supported_host()
    linux.write_text("ID=fedora")
    monkeypatch.setattr(installer.shutil, "which", lambda _: None)
    with pytest.raises(ToolchainError, match="package manager missing"):
        installer.supported_host()


def test_linux_sdk_archives_work_without_dpkg(linux, monkeypatch):
    monkeypatch.setattr(
        installer.shutil,
        "which",
        lambda name: "/bin/" + name if name == "apt-get" else None,
    )
    downloads = []

    def download(url, destination, checksum):
        downloads.append(url)
        assert checksum and len(checksum) == 64
        name = (
            "tinygo/bin/tinygo"
            if "tinygo" in url
            else "wasi-sdk-34.0-x86_64-linux/bin/clang"
        )
        with tarfile.open(destination, "w:gz") as archive:
            member = tarfile.TarInfo(name)
            member.size = 4
            member.mode = 0o755
            archive.addfile(member, io.BytesIO(b"tool"))

    monkeypatch.setattr(installer, "download", download)
    monkeypatch.setattr(
        installer, "execute", lambda *_: pytest.fail("must not invoke dpkg")
    )
    installer.install_tools(["tinygo", "clang"])
    assert all(url.endswith(".tar.gz") for url in downloads)
    assert (linux.parent / "tools/usr/local/lib/tinygo/bin/tinygo").is_file()
    assert (linux.parent / "tools/opt/wasi-sdk/bin/clang").is_file()


def test_upgrade_refreshes_ready_tools_without_downgrade_or_unlock(macos, monkeypatch):
    report = {
        "tools": [
            {"tool": "python3", "status": "ready", "version": "3.13.3"},
            {"tool": "wasm-tools", "status": "ready", "version": "1.245.1"},
            {"tool": "wkg", "status": "ready", "version": "0.99.0"},
        ]
    }
    monkeypatch.setattr(installer, "discover_local", lambda *_: report)
    assert installer.installation_plan(["python"]) == []
    assert installer.installation_plan(["python"], upgrade=True) == ["wasm-tools"]
    assert (
        installer.installation_plan(
            ["python"],
            upgrade=True,
            profiles={"python": {"versions": {"wasm-tools": "1.245.1"}}},
        )
        == []
    )
    assert (
        installer.installation_plan(
            ["python"],
            upgrade=True,
            profiles={"python": {"tools": {"wasm-tools": "/custom/wasm-tools"}}},
        )
        == []
    )
    with pytest.raises(ToolchainError, match="Locked wasm-tools"):
        installer.installation_plan(
            ["python", "c"],
            upgrade=True,
            profiles={"c": {"versions": {"wasm-tools": "1.245.1"}}},
        )


def test_npm_replacement_protects_ready_sibling_lock(macos, monkeypatch):
    report = {
        "tools": [
            {
                "tool": name,
                "status": "missing" if name == "componentize-js" else "ready",
            }
            for name in tools_for("js")
        ]
    }
    monkeypatch.setattr(installer, "discover_local", lambda *_: report)
    with pytest.raises(ToolchainError, match="Locked jco"):
        installer.installation_plan(
            ["js"], upgrade=True, profiles={"js": {"versions": {"jco": "1.40.0"}}}
        )
    with pytest.raises(ToolchainError, match="explicit npm selection"):
        installer.installation_plan(
            ["js"], upgrade=True, profiles={"js": {"tools": {"jco": "/custom/jco"}}}
        )


def test_release_replacement_removes_obsolete_files_and_rolls_back(
    tmp_path, monkeypatch
):
    source = tmp_path / "release"
    source.mkdir()
    (source / "binary").write_bytes(b"new")
    installed = tmp_path / "installed"
    installed.mkdir()
    (installed / "obsolete").write_bytes(b"old")
    installer.replace_release_tree(source, installed)
    assert not (installed / "obsolete").exists()
    assert (installed / "binary").read_bytes() == b"new"
    from pathlib import Path

    rename = Path.rename

    def fail_publish(path, destination):
        if path.name == "new":
            raise OSError("publish failed")
        return rename(path, destination)

    monkeypatch.setattr(Path, "rename", fail_publish)
    with pytest.raises(OSError, match="publish failed"):
        installer.replace_release_tree(source, installed)
    assert (installed / "binary").read_bytes() == b"new"
    assert not list(tmp_path.glob(".release-*"))


@pytest.mark.parametrize("interrupted,rollback_fails", [(True, False), (False, True)])
def test_release_replacement_preserves_backup_when_interrupted(
    tmp_path, monkeypatch, interrupted, rollback_fails
):
    from pathlib import Path

    source = tmp_path / "release"
    source.mkdir()
    (source / "binary").write_bytes(b"new")
    installed = tmp_path / "installed"
    installed.mkdir()
    (installed / "binary").write_bytes(b"old")
    rename = Path.rename

    def fail(path, destination):
        if path.name == "new":
            if interrupted:
                raise KeyboardInterrupt()
            raise OSError("publish failed")
        if rollback_fails and path.name == "previous":
            raise OSError("restore failed")
        return rename(path, destination)

    monkeypatch.setattr(Path, "rename", fail)
    with pytest.raises(KeyboardInterrupt if interrupted else ToolchainError):
        installer.replace_release_tree(source, installed)
    if rollback_fails:
        assert next(tmp_path.glob(".release-*/previous/binary")).read_bytes() == b"old"
    else:
        assert (installed / "binary").read_bytes() == b"old"
        assert not list(tmp_path.glob(".release-*"))


def test_tinygo_optimizer_failure_preserves_installed_release(macos, monkeypatch):
    root = macos / "tools/usr/local/lib/tinygo"
    (root / "bin").mkdir(parents=True)
    (root / "bin/tinygo").write_bytes(b"old compiler")
    (root / "bin/wasm-opt").write_bytes(b"old optimizer")

    def download(url, destination, checksum):
        if "binaryen" in url:
            raise ToolchainError("optimizer download failed")
        with tarfile.open(destination, "w:gz") as archive:
            member = tarfile.TarInfo("tinygo/bin/tinygo")
            member.size = 3
            archive.addfile(member, io.BytesIO(b"new"))

    monkeypatch.setattr(installer, "download", download)
    with pytest.raises(ToolchainError, match="optimizer download failed"):
        installer.install_tools(["tinygo"])
    assert (root / "bin/tinygo").read_bytes() == b"old compiler"
    assert (root / "bin/wasm-opt").read_bytes() == b"old optimizer"


def test_npm_install_pins_legacy_componentize_alias(macos, monkeypatch):
    import json

    root = macos / "tools"
    alias = (
        root
        / "lib/node_modules/@bytecodealliance/jco/node_modules/@bytecodealliance/componentize-js-0-19-3"
    )
    alias.mkdir(parents=True)
    (alias / "package.json").write_text(
        json.dumps({"name": "@bytecodealliance/componentize-js", "version": "0.19.3"})
    )
    commands = []
    monkeypatch.setattr(installer.shutil, "which", lambda *_a, **_kw: "/npm")
    monkeypatch.setattr(installer, "execute", lambda argv, env: commands.append(argv))
    installer.install_tools(["jco", "componentize-js", "preview2-shim"])
    assert sum("--global" in command for command in commands) == 1
    assert any(
        str(alias) in command and command[-1].endswith("@0.17.8")
        for command in commands
    )

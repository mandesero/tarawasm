import hashlib
import io
import tarfile
from pathlib import Path

import pytest

from tarawasm.toolchains import discovery, installer
from tarawasm.toolchains.catalog import CATALOG, TOOLS, binaryen_version
from tarawasm.toolchains.releases import checksum_for
from tarawasm.toolchains.settings import ToolchainError


@pytest.mark.parametrize(
    "system,architecture,digest",
    [
        (
            "linux",
            "amd64",
            "ca9fc6d055e3889462dea4450a2e42a92242d88b5c362a7ec39bdb563413d78a",
        ),
        (
            "darwin",
            "arm64",
            "f5e0161f212fb69ad4650a4809e3ca66856e184892e80058f0d47abc64151812",
        ),
        (
            "darwin",
            "amd64",
            "e544fe732d7b81f058ac8d2c7303e22031eff734c027295e7a53c3037e4d9e89",
        ),
    ],
)
def test_tinygo_checksum_matches_official_version_and_arch(
    system, architecture, digest
):
    assert checksum_for("tinygo", "0.43.0", system, architecture) == digest
    assert checksum_for("tinygo", "0.42.0", system, architecture) != digest


def test_unknown_archive_is_rejected_without_download(tmp_path, monkeypatch):
    monkeypatch.setattr(
        installer, "download", lambda *_: pytest.fail("must not download")
    )
    with pytest.raises(ValueError, match="No verified SHA256.*0.43.1"):
        installer.install_tinygo(
            "0.43.1", "darwin", "arm64", tmp_path / "tools", tmp_path
        )
    with pytest.raises(ValueError, match="linux/arm64"):
        checksum_for("tinygo", "0.43.0", "linux", "arm64")
    assert not (tmp_path / "tools").exists()


def archive_bytes(entries):
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        for name, content in entries.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            member.mode = 0o755
            archive.addfile(member, io.BytesIO(content))
    return payload.getvalue()


@pytest.mark.parametrize(
    "system,architecture",
    [("linux", "amd64"), ("darwin", "arm64"), ("darwin", "amd64")],
)
def test_tinygo_installs_external_optimizer_for_each_platform(
    tmp_path, monkeypatch, system, architecture
):
    compiler = archive_bytes({"tinygo/bin/tinygo": b"compiler"})
    optimizer = archive_bytes({"binaryen-version_133/bin/wasm-opt": b"optimizer"})
    downloads = []

    def download(url, destination, checksum):
        tool = "binaryen" if "binaryen" in url else "tinygo"
        version = "133" if tool == "binaryen" else "0.43.0"
        assert checksum == checksum_for(tool, version, system, architecture)
        downloads.append(url)
        destination.write_bytes(optimizer if tool == "binaryen" else compiler)

    monkeypatch.setattr(installer, "download", download)
    root = tmp_path / "tools"
    installer.install_tinygo("0.43.0", system, architecture, root, tmp_path)
    assert downloads[0].endswith(f"tinygo0.43.0.{system}-{architecture}.tar.gz")
    binaryen_arch = "x86_64" if architecture == "amd64" else "arm64"
    binaryen_os = "linux" if system == "linux" else "macos"
    assert downloads[1].endswith(
        f"binaryen-version_133-{binaryen_arch}-{binaryen_os}.tar.gz"
    )
    assert (root / "usr/local/lib/tinygo/bin/tinygo").read_bytes() == b"compiler"
    assert (root / "usr/local/lib/tinygo/bin/wasm-opt").read_bytes() == b"optimizer"


@pytest.mark.parametrize(
    "failure", ["tinygo-checksum", "optimizer-checksum", "optimizer-network"]
)
@pytest.mark.parametrize("existing", [False, True])
def test_failed_install_never_publishes_partial_release(
    tmp_path, monkeypatch, failure, existing
):
    compiler = archive_bytes({"tinygo/bin/tinygo": b"new compiler"})
    optimizer = archive_bytes({"binaryen-version_133/bin/wasm-opt": b"new optimizer"})
    monkeypatch.setattr(
        installer,
        "checksum_for",
        lambda tool, *_: hashlib.sha256(
            optimizer if tool == "binaryen" else compiler
        ).hexdigest(),
    )

    def open_url(url, **_kwargs):
        if "binaryen" in url:
            if failure == "optimizer-network":
                raise OSError("download interrupted")
            return io.BytesIO(
                b"corrupt optimizer" if failure == "optimizer-checksum" else optimizer
            )
        return io.BytesIO(
            b"corrupt compiler" if failure == "tinygo-checksum" else compiler
        )

    monkeypatch.setattr(installer.urllib.request, "urlopen", open_url)
    root = tmp_path / "tools"
    installed = root / "usr/local/lib/tinygo"
    if existing:
        (installed / "bin").mkdir(parents=True)
        (installed / "bin/tinygo").write_bytes(b"old compiler")
        (installed / "bin/wasm-opt").write_bytes(b"old optimizer")
    with pytest.raises(
        (ToolchainError, OSError), match="SHA256 mismatch|download interrupted"
    ):
        installer.install_tinygo("0.43.0", "linux", "amd64", root, tmp_path)
    if existing:
        assert (installed / "bin/tinygo").read_bytes() == b"old compiler"
        assert (installed / "bin/wasm-opt").read_bytes() == b"old optimizer"
    else:
        assert not installed.exists()


def executable(path: Path, output: str, exit_code: int = 0) -> Path:
    path.write_text(f"#!/bin/sh\nprintf '%s\\n' '{output}'\nexit {exit_code}\n")
    path.chmod(0o755)
    return path


@pytest.mark.parametrize(
    "compiler,optimizer,status",
    [
        ("0.42.0", "116", "ready"),
        ("0.43.0", "133", "ready"),
        ("0.43.0", "116", "incompatible"),
        ("0.43.0", "134", "incompatible"),
        ("0.43.0", "unknown", "incompatible"),
        ("0.43.0", None, "missing"),
    ],
)
def test_doctor_checks_selected_optimizer_version(
    tmp_path, monkeypatch, compiler, optimizer, status
):
    monkeypatch.setenv("TARAWASM_DATA_HOME", str(tmp_path / "managed"))
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("WASMOPT", raising=False)
    executable(tmp_path / "wasm-tools", "wasm-tools 1.261.0")
    executable(tmp_path / "wkg", "wkg 0.16.1")
    executable(tmp_path / "go", "go version go1.27.2")
    executable(tmp_path / "tinygo", f"tinygo version {compiler}")
    if optimizer:
        executable(tmp_path / "wasm-opt", f"wasm-opt version {optimizer}")
    report = discovery.discover_local("go")
    row = next(row for row in report["tools"] if row["tool"] == "tinygo")
    assert row["status"] == status
    assert report["ready"] == (status == "ready")
    assert row["optimizer"]["supported"] == binaryen_version(compiler)


def test_wasmopt_override_and_compilation_environment_agree(tmp_path, monkeypatch):
    monkeypatch.setenv("TARAWASM_DATA_HOME", str(tmp_path / "managed"))
    monkeypatch.setenv("PATH", str(tmp_path))
    compiler = executable(tmp_path / "tinygo", "tinygo version 0.43.0")
    executable(tmp_path / "wasm-opt", "wasm-opt version 116")
    selected = executable(tmp_path / "selected-opt", "wasm-opt version 133")
    monkeypatch.setenv("WASMOPT", str(selected))
    env = discovery.local_environment({"mode": "local"}, language="go")
    assert env["WASMOPT"] == str(selected)
    assert discovery.optimizer_report(str(compiler), "0.43.0", env)["status"] == "ready"
    monkeypatch.delenv("WASMOPT")
    # PATH is selected explicitly for both doctor and the actual TinyGo process.
    env = discovery.local_environment({"mode": "local"}, language="go")
    assert env["WASMOPT"] == str(tmp_path / "wasm-opt")
    assert (
        discovery.optimizer_report(str(compiler), "0.43.0", env)["status"]
        == "incompatible"
    )


def test_optimizer_that_cannot_run_is_not_ready(tmp_path):
    optimizer = executable(tmp_path / "wasm-opt", "wasm-opt version 133", 1)
    row = discovery.optimizer_report(
        "/tinygo", "0.43.0", {"PATH": "/usr/bin", "WASMOPT": str(optimizer)}
    )
    assert row["status"] == "incompatible"
    assert "cannot report" in row["detail"]


def test_upgrade_plan_updates_042_bundle_without_overwriting_custom_go(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(installer, "supported_host", lambda: None)
    monkeypatch.setattr(
        installer,
        "discover_local",
        lambda *_: {
            "tools": [
                {"tool": "go", "status": "ready", "version": "1.27.1"},
                {"tool": "tinygo", "status": "ready", "version": "0.42.0"},
            ]
        },
    )
    assert installer.installation_plan(["go"]) == []
    assert installer.installation_plan(["go"], upgrade=True) == ["go", "tinygo"]
    assert installer.installation_plan(
        ["go"], upgrade=True, profiles={"go": {"tools": {"go": "/custom/go"}}}
    ) == ["tinygo"]
    assert TOOLS["tinygo"]["recommended"] == "0.43.0"
    assert (
        binaryen_version(TOOLS["tinygo"]["recommended"])
        == CATALOG["packages"]["binaryen"]
    )


@pytest.mark.parametrize("language", ["python", "js", "rust", "c"])
def test_other_languages_do_not_get_a_go_optimizer_override(
    tmp_path, monkeypatch, language
):
    monkeypatch.setenv("TARAWASM_DATA_HOME", str(tmp_path / "managed"))
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("WASMOPT", raising=False)
    executable(tmp_path / "tinygo", "tinygo version 0.43.0")
    executable(tmp_path / "wasm-opt", "wasm-opt version 133")
    assert "WASMOPT" not in discovery.local_environment(
        {"mode": "local"}, language=language
    )

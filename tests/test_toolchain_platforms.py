"""Opt-in real installer/ABI checks on the supported Linux distribution matrix."""

import os
import subprocess
from pathlib import Path

import pytest

PLATFORMS = ("debian-bookworm", "fedora-39", "centos-8", "redos-7.3", "astra-1.7")

INSTALL_CHECK = r"""
import os, subprocess
from pathlib import Path
from tarawasm.toolchains.catalog import TOOLS
from tarawasm.toolchains.installer import prerequisite_commands, execute, install_tools
from tarawasm.toolchains.discovery import managed_environment
names = ["go", "tinygo", "node", "clang", "componentize-py", "rustc"]
for command in prerequisite_commands(names):
    execute(command, os.environ.copy())
install_tools(names)
env = managed_environment()
for name in names:
    command = [name, *TOOLS[name]["version_args"]]
    print(subprocess.check_output(command, env=env, text=True))
root = Path("/tmp/check")
root.mkdir()
(root / "hello.go").write_text("package main\nfunc main() {}\n")
(root / "hello.c").write_text("int add(int a, int b) { return a+b; }")
(root / "hello.rs").write_text("pub fn add(a: i32, b: i32) -> i32 { a+b }")
subprocess.run(["tinygo", "build", "-target=wasip1", "-o", str(root / "go.wasm"), str(root / "hello.go")], env={**env, "GOTOOLCHAIN": "local"}, check=True)
subprocess.run(["clang", "-mexec-model=reactor", str(root / "hello.c"), "-o", str(root / "c.wasm")], env=env, check=True)
subprocess.run(["rustc", "--target", "wasm32-wasip1", "--crate-type", "cdylib", str(root / "hello.rs"), "-o", str(root / "rust.wasm")], env=env, check=True)
subprocess.run(["npm", "--version"], env=env, check=True)
for name in ("go", "c", "rust"):
    assert (root / (name + ".wasm")).read_bytes().startswith(b"\x00asm")
print("PLATFORM INSTALLER CHECK PASSED")
"""


@pytest.mark.parametrize("platform", PLATFORMS)
def test_linux_distribution_installs_managed_releases(platform):
    if os.environ.get("TARAWASM_PLATFORM_TOOLCHAIN_IT") != "1":
        pytest.skip("TARAWASM_PLATFORM_TOOLCHAIN_IT is not enabled")
    python_root = os.environ.get("TARAWASM_PLATFORM_PYTHON_ROOT")
    assert python_root and (Path(python_root) / "bin/python3").is_file()
    source = Path(
        os.environ.get("TARAWASM_PLATFORM_SOURCE", Path(__file__).resolve().parents[1])
    )
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/amd64",
            "--entrypoint",
            "/opt/python/bin/python3",
            "--mount",
            f"type=bind,src={python_root},dst=/opt/python,readonly",
            "--mount",
            f"type=bind,src={source},dst=/source,readonly",
            "-e",
            "PYTHONPATH=/source",
            "-e",
            "TARAWASM_DATA_HOME=/tmp/toolchains",
            "-e",
            "PATH=/opt/python/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            f"packpack/packpack:{platform}",
            "-c",
            INSTALL_CHECK,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PLATFORM INSTALLER CHECK PASSED" in result.stdout

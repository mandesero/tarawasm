"""Exercise a saved local profile using real installed tools on the host."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tarawasm.toolchains.catalog import LANGUAGES


@pytest.mark.parametrize("language", LANGUAGES)
def test_host_uses_selected_local_toolchain(tmp_path, language):
    if os.environ.get("TARAWASM_LOCAL_TOOLCHAIN_IT") != "1":
        pytest.skip("TARAWASM_LOCAL_TOOLCHAIN_IT is not enabled")
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(PYTHONPATH=str(root), TARAWASM_CONFIG_HOME=str(tmp_path / "config"))
    env.pop("INSIDE_DOCKER", None)
    env.pop("TARAWASM_TOOLCHAIN_LANGUAGE", None)
    project = tmp_path / "project"
    project.mkdir()
    shutil.copy2(
        root / f"examples/{language}/docs:adder@0.1.0.wasm", project / "input.wasm"
    )

    def invoke(*args):
        result = subprocess.run(
            [sys.executable, "-m", "tarawasm.cli", "--non-interactive", *args],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result

    invoke("toolchain", "use", language, "--mode", "local")
    invoke(
        "import",
        "--lang",
        language,
        "--component",
        "input.wasm",
        "--world",
        "adder",
        ".",
    )
    invoke("toolchain", "use", language, "--mode", "local", "--project")
    invoke("bind")
    invoke("build")
    external = tmp_path / "external/component.wasm"
    invoke("build", "--out", str(external))
    assert external.read_bytes().startswith(b"\x00asm\x0d\x00\x01\x00")
    invoke("strip", str(external))
    assert external.with_suffix(".strip.wasm").is_file()
    report = json.loads(invoke("toolchain", "status", language, "--json").stdout)[
        "reports"
    ][0]
    assert report["ready"] and report["mode"] == "local"
    invoke("clean")
    assert (project / "input.wasm").is_file()
    assert not external.exists()

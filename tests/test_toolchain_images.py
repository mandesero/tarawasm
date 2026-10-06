"""Exercise host-side environment selection and whole-operation routing."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tarawasm.toolchains.catalog import LANGUAGES


@pytest.mark.parametrize("language", LANGUAGES)
def test_host_routes_selected_docker_toolchain(tmp_path, language):
    pattern = os.environ.get("TARAWASM_LANGUAGE_IMAGE_PATTERN")
    if not pattern:
        pytest.skip("TARAWASM_LANGUAGE_IMAGE_PATTERN is not configured")
    image = pattern.format(language=language)
    if not shutil.which("docker"):
        pytest.skip("Docker CLI unavailable")
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(
        PYTHONPATH=str(root),
        TARAWASM_CONFIG_HOME=str(tmp_path / "config"),
        TARAWASM_DATA_HOME=str(tmp_path / "data"),
    )
    env.pop("INSIDE_DOCKER", None)
    project = tmp_path / "project"
    project.mkdir()
    fixture = root / f"examples/{language}/docs:adder@0.1.0.wasm"
    shutil.copy2(fixture, project / "input.wasm")

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

    invoke("toolchain", "use", language, "--mode", "docker", "--image", image)
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
    if language == "python":
        external_wit = tmp_path / "external-wit"
        shutil.copytree(project / ".tarawasm/imported-wit", external_wit)
        config_path = project / "tarawasm.json"
        config = json.loads(config_path.read_text())
        config["wit"]["path"] = str(external_wit)
        config_path.write_text(json.dumps(config))
        invoke("deps", "resolve")
        invoke("deps", "update")
        assert (project / "wkg.lock").is_file()
    invoke("bind")
    invoke("build")
    previous = (project / "dist/adder.wasm").read_bytes()
    assert previous.startswith(b"\x00asm\x0d\x00\x01\x00")
    # This is outside the mounted project and exercises explicit output mounts.
    external = tmp_path / "external/component.wasm"
    invoke("build", "--out", str(external))
    assert external.read_bytes().startswith(b"\x00asm\x0d\x00\x01\x00")
    invoke("strip", str(external))
    assert external.with_suffix(".strip.wasm").is_file()
    report = json.loads(invoke("toolchain", "status", language, "--json").stdout)
    assert report["reports"][0]["ready"] is True
    assert report["reports"][0]["mode"] == "docker"
    invoke("clean")
    assert not external.exists()
    assert (project / "input.wasm").is_file()
    assert (project / "tarawasm.json").is_file()

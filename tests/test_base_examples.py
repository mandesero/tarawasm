import shutil
from pathlib import Path

import pytest
from utils import CLI_MODES, cli_mode_available, run_cli

from tarawasm.backends import get_backend

LANGUAGES = ("python", "go", "js", "rust", "c")


@pytest.mark.parametrize("mode", CLI_MODES, ids=lambda value: f"cli:{value}")
@pytest.mark.parametrize("language", LANGUAGES, ids=lambda value: f"lang:{value}")
def test_import_bind_build(language, tmp_path, mode):
    if not cli_mode_available(mode):
        pytest.skip(f"CLI mode '{mode}' not available in this environment")
    if mode != "docker" and get_backend(language).doctor():
        pytest.skip(
            f"Local {language} toolchain is incomplete: "
            f"{', '.join(get_backend(language).doctor())}"
        )
    fixture = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / language
        / "docs:adder@0.1.0.wasm"
    )
    shutil.copy(fixture, tmp_path / "input.wasm")
    run_cli(
        tmp_path,
        "import",
        "--lang",
        language,
        "--component",
        "input.wasm",
        "--world",
        "adder",
        ".",
        mode=mode,
    )
    run_cli(tmp_path, "bind", mode=mode)
    run_cli(tmp_path, "build", mode=mode)
    assert (tmp_path / "dist/adder.wasm").is_file()


@pytest.mark.parametrize("language", LANGUAGES, ids=lambda value: f"lang:{value}")
def test_wit_first_bind_build_in_docker(language, tmp_path):
    if not cli_mode_available("docker"):
        pytest.skip("Docker CLI mode is not available in this environment")
    fixture = Path(__file__).resolve().parents[1] / "examples" / language / "wit"
    shutil.copytree(fixture, tmp_path / "wit")
    run_cli(
        tmp_path,
        "init",
        "--lang",
        language,
        "--wit",
        "wit",
        "--world",
        "adder",
        ".",
        mode="docker",
    )
    run_cli(tmp_path, "bind", mode="docker")
    run_cli(tmp_path, "build", mode="docker")
    assert (tmp_path / "dist/adder.wasm").is_file()

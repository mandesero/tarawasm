import shutil
import subprocess
from pathlib import Path

import pytest
from utils import cli_mode_available, run_cli, run_tool


def _create_local_python_package(work_dir: Path) -> Path:
    pkg_root = work_dir / "localdep"
    pkg_module = pkg_root / "tarawasm_test_helper"
    pkg_module.mkdir(parents=True)

    (pkg_root / "setup.py").write_text(
        "from setuptools import setup\n"
        "\n"
        "setup(\n"
        "    name='tarawasm-test-helper',\n"
        "    version='0.1.0',\n"
        "    packages=['tarawasm_test_helper'],\n"
        ")\n"
    )
    (pkg_module / "__init__.py").write_text(
        "def banner() -> str:\n" "    return 'helper-ok'\n"
    )
    return pkg_root


@pytest.mark.parametrize("mode", ["docker"], ids=lambda m: f"cli:{m}")
def test_docker_pip_install_unblocks_python_build(tmp_path, mode):
    if not cli_mode_available(mode):
        pytest.skip(f"CLI mode '{mode}' not available in this environment")

    wasm_src = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "python"
        / "docs:adder@0.1.0.wasm"
    )
    work_dir = tmp_path
    shutil.copy(wasm_src, work_dir)
    _create_local_python_package(work_dir)

    run_cli(
        work_dir,
        "init",
        "--lang",
        "python",
        "--wasm-file",
        "docs:adder@0.1.0.wasm",
        "adder",
        mode=mode,
    )
    run_cli(work_dir, "bind", mode=mode)

    (work_dir / "main.py").write_text(
        "from wit_world import exports\n"
        "import tarawasm_test_helper\n"
        "\n"
        "class Run(exports.Run):\n"
        "    def run(self) -> None:\n"
        "        print(tarawasm_test_helper.banner())\n"
    )

    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        run_tool(work_dir, "build", mode=mode, capture_output=True, text=True)
    assert "No module named 'tarawasm_test_helper'" in (
        (exc_info.value.stderr or "") + (exc_info.value.stdout or "")
    )

    run_cli(work_dir, "pip", "install", "./localdep", mode=mode)
    run_cli(work_dir, "build", mode=mode)

    assert (work_dir / "adder.wasm").exists()
    assert (
        work_dir
        / ".tarawasm"
        / "site-packages"
        / "tarawasm_test_helper"
        / "__init__.py"
    ).exists()

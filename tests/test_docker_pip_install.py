import os
import shutil
import subprocess
import sys
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
        "def banner() -> str:\n    return 'helper-ok'\n"
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
        "import",
        "--lang",
        "python",
        "--component",
        "docs:adder@0.1.0.wasm",
        "--world",
        "adder",
        ".",
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

    (work_dir / "requirements.txt").write_text("./localdep\n")
    run_cli(work_dir, "pip", "install", "-r", "requirements.txt", mode=mode)
    run_cli(work_dir, "build", mode=mode)

    assert (work_dir / "dist" / "adder.wasm").exists()
    assert (
        work_dir
        / ".tarawasm"
        / "site-packages"
        / "tarawasm_test_helper"
        / "__init__.py"
    ).exists()

    package_info = run_tool(
        work_dir,
        "pip",
        "show",
        "tarawasm-test-helper",
        mode=mode,
        capture_output=True,
        text=True,
    )
    assert "Location: /work/.tarawasm/site-packages" in package_info.stdout
    dependency_check = run_tool(
        work_dir,
        "pip",
        "check",
        mode=mode,
        capture_output=True,
        text=True,
    )
    assert "No broken requirements found" in dependency_check.stdout

    run_cli(work_dir, "clean", mode=mode)
    assert not (work_dir / "dist" / "adder.wasm").exists()
    assert (
        work_dir
        / ".tarawasm"
        / "site-packages"
        / "tarawasm_test_helper"
        / "__init__.py"
    ).exists()

    # A fresh container can build with the same persisted dependencies.
    run_cli(work_dir, "build", mode=mode)
    assert (work_dir / "dist" / "adder.wasm").exists()

    run_cli(
        work_dir,
        "pip",
        "uninstall",
        "--yes",
        "tarawasm-test-helper",
        mode=mode,
    )
    assert not (
        work_dir
        / ".tarawasm"
        / "site-packages"
        / "tarawasm_test_helper"
        / "__init__.py"
    ).exists()
    with pytest.raises(subprocess.CalledProcessError):
        run_tool(
            work_dir,
            "pip",
            "show",
            "tarawasm-test-helper",
            mode=mode,
            capture_output=True,
            text=True,
        )


@pytest.mark.parametrize("mode", ["docker"], ids=lambda m: f"cli:{m}")
def test_docker_pip_rejects_install_location_overrides(tmp_path, mode):
    if not cli_mode_available(mode):
        pytest.skip(f"CLI mode '{mode}' not available in this environment")

    _create_local_python_package(tmp_path)
    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        run_tool(
            tmp_path,
            "pip",
            "install",
            "--target",
            "elsewhere",
            "./localdep",
            mode=mode,
            capture_output=True,
            text=True,
        )

    output = (exc_info.value.stderr or "") + (exc_info.value.stdout or "")
    assert "pip install location is managed" in output
    assert not (tmp_path / "elsewhere").exists()


@pytest.mark.parametrize("mode", ["docker"], ids=lambda m: f"cli:{m}")
def test_installed_cli_docker_uses_project_packages_not_host_site(tmp_path, mode):
    """A wheel-installed CLI must build with container-installed dependencies."""
    if not cli_mode_available(mode):
        pytest.skip(f"CLI mode '{mode}' not available in this environment")
    root = Path(__file__).resolve().parents[1]
    wheels = tmp_path / "wheels"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "-w",
            str(wheels),
            str(root),
        ],
        check=True,
    )
    venv = tmp_path / "host-python"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    python = str(venv / "bin/python")
    cli = str(venv / "bin/tarawasm")
    env = os.environ.copy()
    for key in ("PYTHONPATH", "INSIDE_DOCKER", "TARAWASM_PY_SITE_PACKAGES"):
        env.pop(key, None)
    env.update(
        TARAWASM_CONFIG_HOME=str(tmp_path / "config"),
        TARAWASM_DATA_HOME=str(tmp_path / "data"),
    )
    project = tmp_path / "project"
    project.mkdir()
    _create_local_python_package(project)
    (project / "requirements.txt").write_text("./localdep\n")
    subprocess.run(
        [
            python,
            "-m",
            "pip",
            "install",
            str(next(wheels.glob("tarawasm-*.whl"))),
            "-r",
            "requirements.txt",
        ],
        cwd=project,
        env=env,
        check=True,
    )
    # The dependency is installed and importable by the same Python as the CLI.
    subprocess.run(
        [
            python,
            "-c",
            "import tarawasm_test_helper; assert tarawasm_test_helper.banner() == 'helper-ok'",
        ],
        cwd=project,
        env=env,
        check=True,
    )

    def invoke(*args):
        return subprocess.run(
            [cli, "--non-interactive", *args],
            check=False,
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
        )

    image = os.environ.get("TARAWASM_DOCKER_IMAGE", "mandeser0/tarawasm:latest")
    selected = invoke(
        "toolchain", "use", "python", "--mode", "docker", "--image", image
    )
    assert selected.returncode == 0, selected.stdout + selected.stderr
    shutil.copy2(root / "examples/python/docs:adder@0.1.0.wasm", project / "input.wasm")
    imported = invoke(
        "import",
        "--lang",
        "python",
        "--component",
        "input.wasm",
        "--world",
        "adder",
        ".",
    )
    assert imported.returncode == 0, imported.stdout + imported.stderr
    bound = invoke("bind")
    assert bound.returncode == 0, bound.stdout + bound.stderr
    (project / "main.py").write_text(
        "from wit_world import exports\n"
        "import tarawasm_test_helper\n"
        "assert tarawasm_test_helper.banner() == 'helper-ok'\n"
        "class Run(exports.Run):\n"
        "    def run(self) -> None:\n"
        "        print(tarawasm_test_helper.banner())\n"
    )
    missing = invoke("build")
    assert missing.returncode != 0
    assert "No module named 'tarawasm_test_helper'" in missing.stdout + missing.stderr
    assert not (project / "dist/adder.wasm").exists()

    # Install through the image entrypoint, just like the full-Docker helper.
    run_cli(project, "pip", "install", "-r", "requirements.txt", mode=mode)
    assert (
        project / ".tarawasm/site-packages/tarawasm_test_helper/__init__.py"
    ).is_file()
    # Force the host CLI to start a fresh container for every operation.
    for args in (("build",), ("clean",), ("build",)):
        result = invoke(*args)
        assert result.returncode == 0, result.stdout + result.stderr
    assert (project / "dist/adder.wasm").read_bytes().startswith(b"\0asm\x0d\0\x01\0")

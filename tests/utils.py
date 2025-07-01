import os
import shutil
import subprocess
import sys
from pathlib import Path

RUNTIME = os.environ.get("WASM_RUNTIME", "wasmtime")
CLI_MODES = ["python", "docker", "standalone"]
_BASE_DOCKER_IMAGE = "mandeser0/tarawasm:latest"


def _get_docker_images():
    try:
        out = subprocess.check_output(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"], text=True
        )
        return out.splitlines()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []


def cli_mode_available(mode):
    if mode == "python":
        return True
    elif mode == "docker":
        docker_image = os.environ.get("TARAWASM_DOCKER_IMAGE", _BASE_DOCKER_IMAGE)
        return shutil.which("docker") and docker_image in _get_docker_images()
    elif mode == "standalone":
        return shutil.which("tarawasm") is not None
    else:
        return False


def runtime_available() -> bool:
    """Return True if the chosen runtime binary is present."""
    return shutil.which(RUNTIME) is not None


def clang_supports_wasm() -> bool:
    """Check if system clang can target WebAssembly."""
    try:
        out = subprocess.check_output(["clang", "--version"], text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    return "wasm32-unknown-wasi" in out


def run_cli(tmpdir, *args, mode="python"):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    workdir = Path(tmpdir).resolve()

    if mode == "python":
        cmd = [sys.executable, "-m", "tarawasm.cli", *args]
    elif mode == "docker":
        docker_image = os.environ.get("TARAWASM_DOCKER_IMAGE", _BASE_DOCKER_IMAGE)
        if not cli_mode_available("docker"):
            raise RuntimeError(f"Docker image '{docker_image}' not found locally.")
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{workdir}:/work",
            "-w",
            "/work",
            docker_image,
            *args,
        ]
    elif mode == "standalone":
        if not cli_mode_available("standalone"):
            raise RuntimeError("Standalone binary 'tarawasm' not found in PATH.")
        cmd = ["tarawasm", *args]
    else:
        raise ValueError(
            f"Unsupported mode '{mode}'. Allowed: python, docker, standalone."
        )

    subprocess.run(cmd, check=True, cwd=tmpdir, env=env)

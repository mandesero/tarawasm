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


def _docker_run_prefix(workdir: Path) -> list[str]:
    docker_platform = os.environ.get("TARAWASM_DOCKER_PLATFORM")
    cmd = ["docker", "run", "--rm"]
    if docker_platform:
        cmd.extend(["--platform", docker_platform])
    cmd.extend(["-v", f"{workdir}:/work", "-w", "/work"])
    return cmd


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


def runtime_available(cli_mode: str | None = None) -> bool:
    """Return True if runtime is available for the selected CLI mode."""
    runtime_mode = os.environ.get("TARAWASM_RUNTIME_MODE", "host")
    if cli_mode == "docker" and runtime_mode == "docker":
        return bool(cli_mode_available("docker"))
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
        cmd = _docker_run_prefix(workdir) + [docker_image, *args]
    elif mode == "standalone":
        if not cli_mode_available("standalone"):
            raise RuntimeError("Standalone binary 'tarawasm' not found in PATH.")
        cmd = ["tarawasm", *args]
    else:
        raise ValueError(
            f"Unsupported mode '{mode}'. Allowed: python, docker, standalone."
        )

    subprocess.run(cmd, check=True, cwd=tmpdir, env=env)


def run_runtime(tmpdir, wasm_file, mode="python"):
    workdir = Path(tmpdir).resolve()
    wasm_path = Path(wasm_file)
    if not wasm_path.is_absolute():
        wasm_path = (workdir / wasm_path).resolve()

    runtime_mode = os.environ.get("TARAWASM_RUNTIME_MODE", "host")
    if mode == "docker" and runtime_mode == "docker":
        docker_image = os.environ.get("TARAWASM_DOCKER_IMAGE", _BASE_DOCKER_IMAGE)
        if not cli_mode_available("docker"):
            raise RuntimeError(f"Docker image '{docker_image}' not found locally.")
        try:
            wasm_rel = wasm_path.relative_to(workdir).as_posix()
            wasm_arg = f"/work/{wasm_rel}"
        except ValueError:
            wasm_arg = str(wasm_path)
        cmd = _docker_run_prefix(workdir) + [docker_image, RUNTIME, wasm_arg]
        return subprocess.run(cmd, capture_output=True, text=True, check=True)

    return subprocess.run(
        [RUNTIME, str(wasm_path)], capture_output=True, text=True, check=True
    )

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

LANG_EXPECTED = {
    "python": "Hello from Python WASM!",
    "go": "Hello from Go WASM!",
    "js": "Hello from JS WASM!",
    "rust": "Hello from Rust WASM!",
    "c": "Hello from C WASM!",
}

RUNTIME = os.environ.get("WASM_RUNTIME", "wasmtime")


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


pytestmark = pytest.mark.skipif(
    not runtime_available(), reason=f"'{RUNTIME}' runtime is not available"
)


def run_cli(tmpdir, *args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    cmd = [sys.executable, "-m", "tarawasm.cli", *args]
    subprocess.run(cmd, check=True, cwd=tmpdir, env=env)


@pytest.mark.parametrize("lang,expected", LANG_EXPECTED.items())
def test_examples(lang, expected, tmp_path):
    if lang == "c" and not clang_supports_wasm():
        pytest.skip("clang is not built with wasm32-unknown-wasi target")

    wasm_src = Path(__file__).resolve().parents[1] / "examples" / lang / "docs:adder@0.1.0.wasm"
    work_dir = tmp_path
    shutil.copy(wasm_src, work_dir)

    run_cli(work_dir, "init", "--lang", lang, "--wasm-file", "docs:adder@0.1.0.wasm", "adder")
    run_cli(work_dir, "bind")
    run_cli(work_dir, "build")

    wasm_file = work_dir / ("adder.component.wasm" if lang == "c" else "adder.wasm")
    result = subprocess.run([RUNTIME, str(wasm_file)], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == expected

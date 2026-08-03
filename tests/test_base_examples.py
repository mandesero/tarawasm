import shutil
from pathlib import Path

import pytest
from utils import (
    CLI_MODES,
    clang_supports_wasm,
    cli_mode_available,
    run_cli,
    run_runtime,
    runtime_available,
)

LANG_EXPECTED = {
    "python": "Hello from Python WASM!",
    "go": "Hello from Go WASM!",
    "js": "Hello from JS WASM!",
    "rust": "Hello from Rust WASM!",
    "c": "Hello from C WASM!",
}

@pytest.mark.parametrize("mode", CLI_MODES, ids=lambda m: f"cli:{m}")
@pytest.mark.parametrize("lang,expected", LANG_EXPECTED.items(), ids=lambda x: f"lang:{x}")
def test_examples(lang, expected, tmp_path, mode):
    if not cli_mode_available(mode):
        pytest.skip(f"CLI mode '{mode}' not available in this environment")
    if not runtime_available(mode):
        pytest.skip("Runtime is not available for this mode")

    if mode != "docker" and lang == "c" and not clang_supports_wasm():
        pytest.skip("clang is not built with wasm32-unknown-wasi target")

    wasm_src = Path(__file__).resolve().parents[1] / "examples" / lang / "docs:adder@0.1.0.wasm"
    work_dir = tmp_path
    shutil.copy(wasm_src, work_dir)

    run_cli(work_dir, "init", "--lang", lang, "--wasm-file", "docs:adder@0.1.0.wasm", "adder", mode=mode)
    run_cli(work_dir, "bind", mode=mode)
    run_cli(work_dir, "build", mode=mode)

    wasm_file = work_dir / "dist" / ("adder.component.wasm" if lang == "c" else "adder.wasm")
    result = run_runtime(work_dir, wasm_file, mode=mode)
    assert result.stdout.strip() == expected

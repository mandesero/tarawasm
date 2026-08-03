import shutil
from pathlib import Path

import pytest
from utils import (
    CLI_MODES,
    clang_supports_wasm,
    cli_mode_available,
    run_cli,
    runtime_available,
)

LANGS = ["python", "go", "js", "rust", "c"]


@pytest.mark.parametrize("mode", CLI_MODES, ids=lambda m: f"cli:{m}")
@pytest.mark.parametrize("lang", LANGS, ids=lambda x: f"lang:{x}")
def test_strip_reduces_size(lang, tmp_path, mode):
    if not cli_mode_available(mode):
        pytest.skip(f"CLI mode '{mode}' not available in this environment")
    if not runtime_available(mode):
        pytest.skip("Runtime is not available for this mode")

    if mode != "docker" and lang == "c" and not clang_supports_wasm():
        pytest.skip("clang is not built with wasm32-unknown-wasi target")

    wasm_src = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / lang
        / "docs:adder@0.1.0.wasm"
    )
    work_dir = tmp_path
    shutil.copy(wasm_src, work_dir)

    run_cli(
        work_dir,
        "init",
        "--lang",
        lang,
        "--wasm-file",
        "docs:adder@0.1.0.wasm",
        "adder",
        mode=mode,
    )
    run_cli(work_dir, "bind", mode=mode)
    run_cli(work_dir, "build", mode=mode)

    wasm_filename = "dist/adder.component.wasm" if lang == "c" else "dist/adder.wasm"
    wasm_filepath = work_dir / wasm_filename
    assert wasm_filepath.exists(), f"WASM output file not found: {wasm_filepath}"

    original_size = wasm_filepath.stat().st_size

    run_cli(work_dir, "strip", str(wasm_filename), "--all", mode=mode)

    stripped_file = wasm_filepath.with_name(wasm_filepath.stem + ".strip.wasm")
    assert stripped_file.exists(), f"Stripped file not found: {stripped_file}"

    stripped_size = stripped_file.stat().st_size

    assert (
        stripped_size <= original_size
    ), f"Stripped size ({stripped_size} bytes) not smaller than original ({original_size} bytes) for lang={lang}, mode={mode}"

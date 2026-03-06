import shutil
from pathlib import Path

import pytest
from utils import cli_mode_available, run_cli

BIND_TOOL_FLAGS = {
    "python": ["--help"],
    "go": ["--versioned"],
    "js": ["--quiet"],
    "rust": ["--quiet"],
    "c": ["--rename-world", "adder"],
}

BUILD_TOOL_FLAGS = {
    "python": ["--python-path", "."],
    "go": ["-opt=z"],
    "js": ["--world-name", "adder"],
    "rust": ["--quiet"],
    "c": ["-O0"],
}


@pytest.mark.parametrize("mode", ["docker"], ids=lambda m: f"cli:{m}")
@pytest.mark.parametrize(
    "lang", list(BIND_TOOL_FLAGS.keys()), ids=lambda x: f"lang:{x}"
)
def test_bind_accepts_language_specific_flags(tmp_path, mode, lang):
    if not cli_mode_available(mode):
        pytest.skip(f"CLI mode '{mode}' not available in this environment")

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

    run_cli(work_dir, "bind", "--", *BIND_TOOL_FLAGS[lang], mode=mode)


@pytest.mark.parametrize("mode", ["docker"], ids=lambda m: f"cli:{m}")
@pytest.mark.parametrize(
    "lang", list(BUILD_TOOL_FLAGS.keys()), ids=lambda x: f"lang:{x}"
)
def test_build_accepts_language_specific_flags(tmp_path, mode, lang):
    if not cli_mode_available(mode):
        pytest.skip(f"CLI mode '{mode}' not available in this environment")

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
    run_cli(work_dir, "build", "--", *BUILD_TOOL_FLAGS[lang], mode=mode)

    wasm_file = work_dir / ("adder.component.wasm" if lang == "c" else "adder.wasm")
    assert wasm_file.exists()

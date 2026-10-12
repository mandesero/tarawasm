"""Real Go components: default asyncify scheduling and explicit panic unwinding."""

import os
import shutil
from pathlib import Path

import pytest
from utils import cli_mode_available, run_cli, run_tool, runtime_available

from tarawasm.backends import get_backend

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = """package main

import (
    "fmt"
    "go.bytecodealliance.org/cm"
    run "tarawasm/adder/internal/wasi/cli/run"
)

func init() {
    run.Exports.Run = func() cm.BoolResult {
        probe()
        return 0
    }
}

func main() {}
"""
PROBES = {
    "asyncify": """
func probe() {
    ch := make(chan uint32)
    go func() { ch <- 42 }()
    fmt.Println("asyncify", <-ch)
}
""",
    "explicit": """
func probe() {
    defer func() {
        fmt.Println("recovered", recover())
    }()
    defer fmt.Println("defer-outer")
    func() {
        defer fmt.Println("defer-inner")
        panic("intentional panic")
    }()
    fmt.Println("unexpected return after panic")
}
""",
}


@pytest.mark.parametrize("mode", ["python", "docker"], ids=lambda m: f"cli:{m}")
@pytest.mark.parametrize("scenario", ["asyncify", "explicit"])
def test_go_runtime_mode_component(tmp_path, mode, scenario):
    if not cli_mode_available(mode):
        pytest.skip(f"CLI mode '{mode}' unavailable")
    if mode == "python" and get_backend("go").doctor():
        pytest.skip("Local Go toolchain incomplete")
    version = run_tool(
        tmp_path, "tinygo", "version", mode=mode, capture_output=True, text=True
    ).stdout
    if "version 0.43." not in version:
        pytest.skip("Runtime-mode regression requires TinyGo 0.43")
    runtime_mode = os.environ.get("TARAWASM_GO_RUNTIME_MODE", mode)
    if not runtime_available(runtime_mode):
        pytest.skip(f"Wasm runtime unavailable for '{runtime_mode}'")
    shutil.copytree(ROOT / "examples/go/wit", tmp_path / "wit")
    run_cli(tmp_path, "init", "--lang", "go", "--wit", "wit", ".", mode=mode)
    (tmp_path / "main.go").write_text(PROGRAM + PROBES[scenario])
    run_cli(tmp_path, "bind", mode=mode)
    flags = (
        ["--", "-scheduler=none", "-panic-unwind=explicit"]
        if scenario == "explicit"
        else []
    )
    run_cli(tmp_path, "build", *flags, mode=mode)
    run_cli(tmp_path, "strip", "dist/adder.wasm", "--all", mode=mode)
    component = tmp_path / "dist/adder.strip.wasm"
    assert component.read_bytes()[:8] == b"\x00asm\x0d\x00\x01\x00"
    run_tool(tmp_path, "wasm-tools", "validate", "dist/adder.strip.wasm", mode=mode)
    result = run_tool(
        tmp_path,
        "wasmtime",
        "dist/adder.strip.wasm",
        mode=runtime_mode,
        capture_output=True,
        text=True,
    )
    expected = (
        "asyncify 42\n"
        if scenario == "asyncify"
        else "defer-inner\ndefer-outer\nrecovered intentional panic\n"
    )
    assert result.stdout == expected, result.stdout + result.stderr

"""Compile scaffolds against the real, catalog-pinned Go binding generator."""

import shutil
from pathlib import Path

import pytest
from utils import cli_mode_available, run_cli, run_tool

from tarawasm.backends import get_backend

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/go"


@pytest.mark.parametrize("versioned", [False, True], ids=["default", "versioned"])
@pytest.mark.parametrize("mode", ["python", "docker"], ids=lambda m: f"cli:{m}")
@pytest.mark.parametrize(
    "fixture", ["numeric", "hyphens", "tuples", "world-types", "resources"]
)
def test_go_scaffold_compiles_with_real_bindings(tmp_path, fixture, mode, versioned):
    if not cli_mode_available(mode):
        pytest.skip(f"CLI mode '{mode}' unavailable")
    if mode == "python" and get_backend("go").doctor():
        pytest.skip("Local Go toolchain incomplete")
    wit = tmp_path / "wit"
    wit.mkdir()
    shutil.copy(FIXTURES / f"{fixture}.wit", wit / "fixture.wit")
    # Reuse the complete, versioned WASI definitions maintained by the Go example.
    wasi = (ROOT / "examples/go/wit/adder.wit").read_text()
    (wit / "wasi.wit").write_text("package wasi:" + wasi.split("package wasi:", 1)[1])
    world = {"hyphens": "my-world", "world-types": "people"}.get(fixture, fixture)
    run_cli(tmp_path, "init", "--lang", "go", "--wit", "wit", ".", mode=mode)
    if versioned:
        # A user-owned module/source can choose any module path. As with other
        # bindgen flags that change package layout, its imports must match it;
        # bind must never rewrite the user's implementation.
        mod = tmp_path / "go.mod"
        source = tmp_path / "main.go"
        original = f"tarawasm/{world.replace('-', '_')}"
        custom = "example.org/team/custom-module"
        mod.write_text(mod.read_text().replace(original, custom))
        text = source.read_text().replace(original, custom)
        package = {"hyphens": "my-pkg", "world-types": "people"}.get(fixture, fixture)
        text = text.replace(
            f"/internal/docs/{package}/", f"/internal/docs/{package}/v0.1.0/"
        )
        source.write_text(text)
    source_before_bind = (tmp_path / "main.go").read_bytes()
    # bind/build parse the world and run GoBackend.validate_world without bypasses.
    flags = ["--", "--versioned", "--generate-wit"] if versioned else []
    run_cli(tmp_path, "bind", *flags, mode=mode)
    assert (tmp_path / "main.go").read_bytes() == source_before_bind
    run_cli(tmp_path, "build", "--", "-opt=z", mode=mode)
    component = Path("dist") / f"{world}.wasm"
    assert (tmp_path / component).is_file()
    run_cli(tmp_path, "strip", str(component), "--all", mode=mode)
    stripped = component.with_suffix(".strip.wasm")
    run_tool(tmp_path, "wasm-tools", "validate", str(stripped), mode=mode)

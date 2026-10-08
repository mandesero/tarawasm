"""Compile nested Python sources with their actual import dependencies."""

import json

import pytest
from utils import CLI_MODES, cli_mode_available, run_cli

from tarawasm.backends import get_backend


@pytest.mark.parametrize("mode", CLI_MODES, ids=lambda value: f"cli:{value}")
@pytest.mark.parametrize("override", [False, True], ids=["config", "src-override"])
def test_nested_python_source_imports(tmp_path, monkeypatch, mode, override):
    if not cli_mode_available(mode):
        pytest.skip(f"CLI mode '{mode}' not available")
    if mode != "docker" and get_backend("python").doctor():
        pytest.skip("Local Python toolchain is incomplete")
    monkeypatch.delenv("TARAWASM_PY_SITE_PACKAGES", raising=False)
    (tmp_path / "world.wit").write_text(
        "package test:nested; world calculator { export add: func(a: s32, b: s32) -> s32; }"
    )
    run_cli(tmp_path, "init", "--lang", "python", "--wit", "world.wit", ".", mode=mode)
    run_cli(tmp_path, "bind", mode=mode)
    source = tmp_path / (
        "src with spaces/nested/main.py" if override else "src/main.py"
    )
    source.parent.mkdir(parents=True)
    source.write_text(
        "import wit_world\n"
        "from sibling import add\n"
        "from project_helper import offset\n"
        "assert add(19, 23) + offset == 42\n"
        "class WitWorld(wit_world.WitWorld):\n"
        "    def add(self, a: int, b: int) -> int:\n"
        "        return add(a, b) + offset\n"
    )
    (source.parent / "sibling.py").write_text("def add(a, b): return a + b\n")
    (tmp_path / "project_helper.py").write_text("offset = 0\n")
    # A same-named root module must not shadow the selected source.
    (tmp_path / "main.py").write_text("raise RuntimeError('wrong source selected')\n")
    args = ["build"]
    if override:
        args.extend(["--src", str(source.relative_to(tmp_path))])
        extra = tmp_path / "extra packages"
        extra.mkdir()
        (extra / "extra_helper.py").write_text("extra = 0\n")
        args.extend(["--", "--python-path", str(extra.relative_to(tmp_path))])
        persistent = tmp_path / ".tarawasm/site-packages"
        persistent.mkdir(parents=True, exist_ok=True)
        (persistent / "persistent_helper.py").write_text("value = 42\n")
        source.write_text(
            "from extra_helper import extra\nassert extra == 0\n"
            "from persistent_helper import value\nassert value == 42\n"
            + source.read_text()
        )
        # Use a relative path so it is valid in both native and Docker modes.
        monkeypatch.setenv("TARAWASM_PY_SITE_PACKAGES", ".tarawasm/site-packages")
    else:
        config_path = tmp_path / "tarawasm.json"
        config = json.loads(config_path.read_text())
        config["source"] = str(source.relative_to(tmp_path))
        config_path.write_text(json.dumps(config))
    original = source.read_bytes()
    run_cli(tmp_path, *args, mode=mode)
    # The CLI validates the component before publishing it.
    assert (tmp_path / "dist/calculator.wasm").is_file()
    assert source.read_bytes() == original

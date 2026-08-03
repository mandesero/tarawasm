import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from tarawasm.backends.base import Command
from tarawasm.cli import cli
from tarawasm.config import Config

CALCULATOR_WIT = """package test:calculator@0.1.0;
world calculator { export add: func(a: s32, b: s32) -> s32; }
"""


def _write_project(tmp_path: Path, monkeypatch, language: str = "python") -> Config:
    wit = tmp_path / "calculator.wit"
    wit.write_text(CALCULATOR_WIT)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli, ["init", "--lang", language, "--wit", str(wit), "."]
    )
    assert result.exit_code == 0, result.output
    return Config.load(tmp_path)


@pytest.mark.parametrize(
    "language,source",
    [
        ("python", "main.py"),
        ("go", "main.go"),
        ("js", "main.js"),
        ("rust", "src/lib.rs"),
        ("c", "component.c"),
    ],
)
def test_wit_first_init_for_each_backend(tmp_path, monkeypatch, language, source):
    conf = _write_project(tmp_path, monkeypatch, language)
    assert conf.language == language
    assert conf.world == "calculator"
    assert conf.wit_package == "test:calculator@0.1.0"
    assert conf.source == Path(source)
    assert conf.output == Path("dist/calculator.wasm")
    assert conf.resolve_path(conf.source).is_file()


def test_init_wasm_file_is_standard_unknown_option(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli,
        ["init", "--lang", "python", "--wasm-file", "input.wasm", "project"],
    )
    assert result.exit_code == 2
    assert "No such option '--wasm-file'" in result.output


def test_init_dry_run_does_not_mutate_filesystem(tmp_path, monkeypatch):
    wit = tmp_path / "calculator.wit"
    wit.write_text(CALCULATOR_WIT)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli,
        [
            "init",
            "--lang",
            "python",
            "--wit",
            str(wit),
            "--dry-run",
            "project",
        ],
    )
    assert result.exit_code == 0, result.output
    assert not (tmp_path / "project").exists()
    assert list(tmp_path.iterdir()) == [wit]


def test_init_does_not_overwrite_user_source_even_with_force(tmp_path, monkeypatch):
    conf = _write_project(tmp_path, monkeypatch)
    source = conf.resolve_path(conf.source)
    source.write_text("# user implementation\n")
    result = CliRunner().invoke(
        cli,
        ["init", "--lang", "python", "--wit", "calculator.wit", "--force", "."],
    )
    assert result.exit_code != 0
    assert "Existing source files are never overwritten" in result.output
    assert source.read_text() == "# user implementation\n"


def test_init_ambiguous_world_lists_choices(tmp_path, monkeypatch):
    wit = tmp_path / "multi.wit"
    wit.write_text("package test:multi@0.1.0; world first {} world second {}")
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli, ["init", "--lang", "python", "--wit", str(wit), "project"]
    )
    assert result.exit_code != 0
    assert "multiple worlds: first, second" in result.output
    assert not (tmp_path / "project").exists()


def test_bind_uses_backend_and_passthrough(tmp_path, monkeypatch):
    conf = _write_project(tmp_path, monkeypatch)
    captured = {}
    commands = []

    class FakeBackend:
        def bind_commands(self, loaded, **kwargs):
            captured.update(kwargs)
            assert loaded == conf
            return (Command(("bind-tool", "--base", *kwargs["tool_args"])),)

    monkeypatch.setattr("tarawasm.cli.Config.load", lambda: conf)
    monkeypatch.setattr("tarawasm.cli.get_backend", lambda _name: FakeBackend())
    monkeypatch.setattr("tarawasm.cli._parse_selected_world", lambda *_args: object())
    monkeypatch.setattr(
        "tarawasm.cli.subprocess.run",
        lambda argv, check, env: commands.append((argv, check)),
    )
    result = CliRunner().invoke(
        cli,
        [
            "bind",
            "--world",
            "calculator",
            "--wit",
            "calculator.wit",
            "--",
            "--flag",
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured == {
        "world": "calculator",
        "wit": tmp_path / "calculator.wit",
        "tool_args": ["--flag"],
    }
    assert commands == [(("bind-tool", "--base", "--flag"), True)]


def test_bind_dry_run_does_not_invoke_tool_or_create_manifest(tmp_path, monkeypatch):
    _write_project(tmp_path, monkeypatch)
    result = CliRunner().invoke(cli, ["bind", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Running:" in result.output
    assert not (tmp_path / ".tarawasm/artifacts.json").exists()


def test_component_import_is_first_class_and_does_not_track_original(
    tmp_path, monkeypatch
):
    fixture = (
        Path(__file__).resolve().parents[1] / "examples/python/docs:adder@0.1.0.wasm"
    )
    original = tmp_path / "input.wasm"
    original.write_bytes(fixture.read_bytes())
    project = tmp_path / "project"
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli,
        [
            "import",
            "--lang",
            "python",
            "--component",
            str(original),
            "--world",
            "adder",
            str(project),
        ],
    )
    assert result.exit_code == 0, result.output
    conf = Config.load(project)
    assert conf.wit_path == Path(".tarawasm/imported-wit")
    assert conf.wit_package == "docs:adder@0.1.0"
    assert conf.resolve_path(conf.wit_path).is_dir()
    assert (project / ".tarawasm/imported-wit/deps/cli/package.wit").is_file()
    data = json.loads((project / "tarawasm.json").read_text())
    assert "component" not in data
    assert "wasm_file" not in data
    monkeypatch.chdir(project)
    clean_result = CliRunner().invoke(cli, ["clean"])
    assert clean_result.exit_code == 0
    assert original.is_file()


def test_component_import_rejects_core_module_without_creating_project(
    tmp_path, monkeypatch
):
    core = tmp_path / "core.wasm"
    core.write_bytes(b"\x00asm\x01\x00\x00\x00")
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli,
        [
            "import",
            "--lang",
            "python",
            "--component",
            str(core),
            "project",
        ],
    )
    assert result.exit_code != 0
    assert "not a WebAssembly Component Model binary" in result.output
    assert not (tmp_path / "project").exists()


def test_failed_build_preserves_previous_output(tmp_path, monkeypatch):
    conf = _write_project(tmp_path, monkeypatch)
    output = conf.resolve_path(conf.output)
    output.parent.mkdir()
    output.write_bytes(b"previous component")

    class FailingBackend:
        def validate_world(self, _world):
            return None

        def build_command(self, loaded, **kwargs):
            assert loaded == conf
            return Command(("failing-tool",))

        def finish_build_command(self, *_args, **_kwargs):
            return None

        def locate_artifact(self, _conf, requested):
            return requested

    monkeypatch.setattr("tarawasm.cli.get_backend", lambda _name: FailingBackend())
    monkeypatch.setattr(
        "tarawasm.cli.subprocess.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.CalledProcessError(7, ["failing-tool"])
        ),
    )
    result = CliRunner().invoke(cli, ["build"])
    assert result.exit_code != 0
    assert output.read_bytes() == b"previous component"


def test_custom_output_is_manifested_and_cleaned(tmp_path, monkeypatch):
    conf = _write_project(tmp_path, monkeypatch)
    external = tmp_path.parent / f"{tmp_path.name}-custom.wasm"

    class SuccessfulBackend:
        def validate_world(self, _world):
            return None

        def build_command(self, loaded, **kwargs):
            assert loaded == conf
            return Command(("successful-tool", str(kwargs["output"])))

        def finish_build_command(self, *_args, **_kwargs):
            return None

        def locate_artifact(self, _conf, requested):
            return requested

    def fake_run(argv, check, env):
        assert check is True
        Path(argv[1]).parent.mkdir(parents=True, exist_ok=True)
        Path(argv[1]).write_bytes(b"component")

    monkeypatch.setattr("tarawasm.cli.get_backend", lambda _name: SuccessfulBackend())
    monkeypatch.setattr("tarawasm.cli._parse_selected_world", lambda *_args: object())
    monkeypatch.setattr("tarawasm.cli.subprocess.run", fake_run)
    monkeypatch.setattr("tarawasm.cli.WitParser.parse", lambda *_args: object())
    result = CliRunner().invoke(cli, ["build", "--out", str(external)])
    assert result.exit_code == 0, result.output
    assert external.read_bytes() == b"component"
    manifest = json.loads((tmp_path / ".tarawasm/artifacts.json").read_text())
    assert str(external) in manifest["external_artifacts"]
    clean_result = CliRunner().invoke(cli, ["clean"])
    assert clean_result.exit_code == 0
    assert not external.exists()


def test_dependency_resolve_creates_lock_without_build_side_effects(
    tmp_path, monkeypatch
):
    _write_project(tmp_path, monkeypatch)
    result = CliRunner().invoke(cli, ["deps", "resolve"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "wkg.lock").is_file()
    listed = CliRunner().invoke(cli, ["deps", "list"])
    assert listed.exit_code == 0
    assert "No locked WIT dependencies" in listed.output

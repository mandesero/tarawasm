from pathlib import Path

from click.testing import CliRunner

from tarawasm.cli import clean, cli
from tarawasm.config import LANG_CFGS, Config


def _config(lang: str = "python") -> Config:
    src = LANG_CFGS[lang]["default-src"]
    return Config(
        world="adder",
        lang=lang,
        wit_path=Path("wit"),
        src_file=src,
        wasm_file="docs:adder@0.1.0.wasm",
    )


def test_bind_uses_common_overrides_and_passthrough(monkeypatch):
    conf = _config()
    captured = {}
    commands = []

    monkeypatch.setattr("tarawasm.cli.Config.load", lambda: conf)

    def fake_bind_args(lang, loaded, **kwargs):
        captured["lang"] = lang
        captured["loaded"] = loaded
        captured["kwargs"] = kwargs
        return ["bind-tool"], ["--base-bind"]

    monkeypatch.setattr("tarawasm.cli.bind_args", fake_bind_args)
    monkeypatch.setattr(
        "tarawasm.cli.subprocess.run",
        lambda cmd, check, **_: commands.append((cmd, check)),
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "bind",
            "--world",
            "custom-world",
            "--wit",
            "custom-wit",
            "--",
            "--lang-flag",
            "42",
        ],
    )

    assert result.exit_code == 0
    assert captured["lang"] == "python"
    assert captured["loaded"] == conf
    assert captured["kwargs"] == {
        "world_override": "custom-world",
        "wit_override": Path("custom-wit"),
    }
    assert commands == [(["bind-tool", "--base-bind", "--lang-flag", "42"], True)]


def test_build_uses_common_overrides_and_passthrough(monkeypatch):
    conf = _config()
    captured = {}
    commands = []

    monkeypatch.setattr("tarawasm.cli.Config.load", lambda: conf)

    def fake_build_args(lang, loaded, **kwargs):
        captured["lang"] = lang
        captured["loaded"] = loaded
        captured["kwargs"] = kwargs
        return ["build-tool"], ["--base-build"]

    monkeypatch.setattr("tarawasm.cli.build_args", fake_build_args)
    monkeypatch.setattr(
        "tarawasm.cli.subprocess.run",
        lambda cmd, check, env=None, **_: commands.append((cmd, check, env)),
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "build",
            "--world",
            "custom-world",
            "--src",
            "custom.py",
            "--wit",
            "custom-wit",
            "--out",
            "custom.wasm",
            "--",
            "--lang-flag",
            "42",
        ],
    )

    assert result.exit_code == 0
    assert captured["lang"] == "python"
    assert captured["loaded"] == conf
    assert captured["kwargs"] == {
        "world_override": "custom-world",
        "wit_override": Path("custom-wit"),
        "src_override": "custom.py",
        "out_override": "custom.wasm",
    }
    assert commands[0][0] == ["build-tool", "--base-build", "--lang-flag", "42"]
    assert commands[0][1] is True


def test_build_clean_runs_clean_before_build(monkeypatch):
    conf = _config()
    calls = {"clean": 0, "build": 0}

    monkeypatch.setattr("tarawasm.cli.Config.load", lambda: conf)
    monkeypatch.setattr(
        "tarawasm.cli.build_args", lambda *_args, **_kwargs: (["tool"], [])
    )
    monkeypatch.setattr(
        "tarawasm.cli.subprocess.run",
        lambda cmd, check, env=None, **_: calls.__setitem__(
            "build", calls["build"] + 1
        ),
    )

    original_clean_callback = clean.callback

    def fake_clean_callback(*_args, **_kwargs):
        calls["clean"] += 1

    monkeypatch.setattr(clean, "callback", fake_clean_callback)

    runner = CliRunner()
    result = runner.invoke(cli, ["build", "--clean"])

    monkeypatch.setattr(clean, "callback", original_clean_callback)

    assert result.exit_code == 0
    assert calls["clean"] == 1
    assert calls["build"] == 1


def test_bind_rejects_common_option_in_tool_args():
    runner = CliRunner()
    result = runner.invoke(cli, ["bind", "--", "--world", "late"])

    assert result.exit_code != 0
    assert "Common option '--world' must be provided before '--'." in result.output


def test_build_rejects_common_option_in_tool_args():
    runner = CliRunner()
    result = runner.invoke(cli, ["build", "--", "--out=late.wasm"])

    assert result.exit_code != 0
    assert "Common option '--out' must be provided before '--'." in result.output


def test_bind_requires_separator_for_tool_specific_options():
    runner = CliRunner()
    result = runner.invoke(cli, ["bind", "--tool-specific-flag", "42"])

    assert result.exit_code != 0
    assert "No such option: --tool-specific-flag" in result.output


def test_bind_tool_help_runs_tool_help_only(monkeypatch):
    conf = _config()
    commands = []

    monkeypatch.setattr("tarawasm.cli.Config.load", lambda: conf)

    def fake_bind_args(*_args, **_kwargs):
        return ["bind-tool"], ["--base-bind"]

    monkeypatch.setattr("tarawasm.cli.bind_args", fake_bind_args)
    monkeypatch.setattr(
        "tarawasm.cli.subprocess.run",
        lambda cmd, **kwargs: commands.append((cmd, kwargs)),
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["bind", "--tool-help", "--", "--lang-flag", "42"])

    assert result.exit_code == 0
    assert commands == [(["bind-tool", "--help"], {"check": False})]


def test_build_tool_help_skips_clean_and_runs_help_only(monkeypatch):
    conf = _config()
    calls = {"clean": 0}
    commands = []

    monkeypatch.setattr("tarawasm.cli.Config.load", lambda: conf)

    def fake_build_args(*_args, **_kwargs):
        return ["build-tool"], ["--base-build"]

    monkeypatch.setattr("tarawasm.cli.build_args", fake_build_args)
    monkeypatch.setattr(
        "tarawasm.cli.subprocess.run",
        lambda cmd, **kwargs: commands.append((cmd, kwargs)),
    )

    original_clean_callback = clean.callback

    def fake_clean_callback(*_args, **_kwargs):
        calls["clean"] += 1

    monkeypatch.setattr(clean, "callback", fake_clean_callback)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["build", "--clean", "--tool-help", "--", "--lang-flag", "42"],
    )

    monkeypatch.setattr(clean, "callback", original_clean_callback)

    assert result.exit_code == 0
    assert calls["clean"] == 0
    assert commands == [(["build-tool", "--help"], {"check": False})]


def test_bind_tool_help_uses_correct_tool_per_language(monkeypatch):
    commands = []
    monkeypatch.setattr(
        "tarawasm.cli.subprocess.run",
        lambda cmd, **kwargs: commands.append((cmd, kwargs)),
    )
    runner = CliRunner()

    expected = {
        "python": ["componentize-py"],
        "go": ["go", "tool", "wit-bindgen-go"],
        "js": ["jco", "guest-types"],
        "rust": ["cargo", "component", "bindings"],
        "c": ["wit-bindgen", "c", "docs:adder@0.1.0.wasm"],
    }

    for lang, prefix in expected.items():
        monkeypatch.setattr("tarawasm.cli.Config.load", lambda lang=lang: _config(lang))
        result = runner.invoke(cli, ["bind", "--tool-help"])
        assert result.exit_code == 0
        cmd, kwargs = commands.pop(0)
        assert cmd == prefix + ["--help"]
        assert kwargs == {"check": False}


def test_build_tool_help_uses_correct_tool_per_language(monkeypatch):
    commands = []
    monkeypatch.setattr(
        "tarawasm.cli.subprocess.run",
        lambda cmd, **kwargs: commands.append((cmd, kwargs)),
    )
    runner = CliRunner()

    expected = {
        "python": ["componentize-py"],
        "go": ["tinygo", "build"],
        "js": ["jco", "componentize"],
        "rust": ["cargo", "component", "build"],
        "c": ["clang", "component.c", "adder.c", "adder_component_type.o"],
    }

    for lang, prefix in expected.items():
        monkeypatch.setattr("tarawasm.cli.Config.load", lambda lang=lang: _config(lang))
        result = runner.invoke(cli, ["build", "--tool-help"])
        assert result.exit_code == 0
        cmd, kwargs = commands.pop(0)
        assert cmd == prefix + ["--help"]
        assert kwargs == {"check": False}

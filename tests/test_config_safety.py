import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from tarawasm.artifacts import ArtifactManifest
from tarawasm.cli import cli
from tarawasm.config import Config, ConfigError


def _config_data(**overrides):
    data = {
        "language": "python",
        "world": "calculator",
        "wit": {"path": "wit", "package": "test:calculator@0.1.0"},
        "source": "main.py",
        "output": "dist/calculator.wasm",
    }
    data.update(overrides)
    return data


def _write_config(root: Path, **overrides) -> Path:
    path = root / "tarawasm.json"
    path.write_text(json.dumps(_config_data(**overrides)))
    return path


def test_config_is_discovered_and_paths_are_relative_to_project(tmp_path, monkeypatch):
    _write_config(tmp_path)
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    conf = Config.load()
    assert conf.project_root == tmp_path
    assert conf.resolve_path(conf.wit_path) == tmp_path / "wit"
    assert conf.resolve_path(conf.source) == tmp_path / "main.py"
    assert conf.resolve_path(conf.output) == tmp_path / "dist/calculator.wasm"


def test_config_does_not_migrate_legacy_fields(tmp_path):
    _write_config(tmp_path, wasm_file="input.wasm")
    with pytest.raises(ConfigError, match=r"Unknown config field\(s\): wasm_file"):
        Config.load(tmp_path)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda data: data.update(extra=True), "Unknown config field(s): extra"),
        (
            lambda data: data["wit"].update(extra=True),
            "Unknown config field(s): wit.extra",
        ),
        (lambda data: data.pop("source"), "Missing config field(s): source"),
        (lambda data: data.update(language="ruby"), "field 'language'"),
        (lambda data: data.update(source=""), "field 'source'"),
    ],
)
def test_config_reports_field_validation_errors(tmp_path, mutate, message):
    data = _config_data()
    mutate(data)
    (tmp_path / "tarawasm.json").write_text(json.dumps(data))
    with pytest.raises(
        ConfigError, match=message.replace("(", r"\(").replace(")", r"\)")
    ):
        Config.load(tmp_path)


def test_config_save_writes_only_current_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    conf = Config(
        language="python",
        world="calculator",
        wit_path=Path("wit"),
        wit_package="test:calculator@0.1.0",
        source=Path("main.py"),
        output=Path("dist/calculator.wasm"),
    )
    conf.save()
    assert json.loads((tmp_path / "tarawasm.json").read_text()) == _config_data()


def test_manifest_clean_preserves_preexisting_user_files(tmp_path, monkeypatch):
    _write_config(tmp_path)
    user_files = [
        tmp_path / "target" / "keep.txt",
        tmp_path / "internal" / "keep.go",
        tmp_path / "custom.wasm",
    ]
    for path in user_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("user data")
    manifest = ArtifactManifest(tmp_path, tmp_path / ".tarawasm")
    before = manifest.snapshot()
    generated = tmp_path / "internal" / "generated.go"
    generated.write_text("generated")
    output = tmp_path / "dist" / "calculator.wasm"
    output.parent.mkdir()
    output.write_text("generated")
    manifest.record_created_since(before)
    nested = tmp_path / "nested"
    nested.mkdir()
    monkeypatch.chdir(nested)
    result = CliRunner().invoke(cli, ["clean"])
    assert result.exit_code == 0
    assert "Removed" in result.output
    assert not generated.exists()
    assert not output.exists()
    assert not (tmp_path / "dist").exists()
    for path in user_files:
        assert path.read_text() == "user data"


def test_docker_mode_does_not_change_existing_permissions(tmp_path, monkeypatch):
    protected = tmp_path / "keep.txt"
    protected.write_text("keep")
    protected.chmod(0o640)
    assert os.stat(protected).st_mode & 0o777 == 0o640

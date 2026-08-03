import json
import os
from pathlib import Path

from click.testing import CliRunner

from tarawasm.artifacts import ArtifactManifest
from tarawasm.cli import cli
from tarawasm.config import Config, ConfigError


def _write_config(root: Path, **overrides) -> Path:
    data = {
        "world": "adder",
        "lang": "python",
        "wit_path": "wit",
        "src_file": "main.py",
        "wasm_file": "input.wasm",
        "state_dir": ".tarawasm",
        "dist_dir": "dist",
    }
    data.update(overrides)
    path = root / "tarawasm.json"
    path.write_text(json.dumps(data))
    return path


def test_config_is_discovered_and_paths_are_relative_to_config(tmp_path, monkeypatch):
    _write_config(tmp_path)
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    conf = Config.load()

    assert conf.project_root == tmp_path
    assert conf.wit_path == tmp_path / "wit"
    assert conf.src_file == str(tmp_path / "main.py")
    assert conf.wasm_file == str(tmp_path / "input.wasm")
    assert conf.state_dir == tmp_path / ".tarawasm"
    assert conf.dist_dir == tmp_path / "dist"


def test_config_rejects_legacy_shape_without_managed_directories(tmp_path):
    path = _write_config(tmp_path)
    data = json.loads(path.read_text())
    del data["state_dir"]
    del data["dist_dir"]
    path.write_text(json.dumps(data))

    try:
        Config.load(tmp_path)
    except ConfigError as exc:
        assert "Missing config field(s): dist_dir, state_dir." in str(exc)
    else:
        raise AssertionError("legacy config unexpectedly loaded")


def test_config_rejects_managed_directory_outside_project(tmp_path):
    _write_config(tmp_path, dist_dir="../outside")

    try:
        Config.load(tmp_path)
    except ConfigError as exc:
        assert "field 'dist_dir' must stay inside the project root" in str(exc)
    else:
        raise AssertionError("unsafe dist_dir unexpectedly loaded")


def test_config_save_has_single_unversioned_schema(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    conf = Config(
        "adder",
        "python",
        Path("wit"),
        "main.py",
        "input.wasm",
    )

    conf.save()

    assert json.loads((tmp_path / "tarawasm.json").read_text()) == {
        "world": "adder",
        "lang": "python",
        "wit_path": "wit",
        "src_file": "main.py",
        "wasm_file": "input.wasm",
        "state_dir": ".tarawasm",
        "dist_dir": "dist",
    }


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
    output = tmp_path / "dist" / "adder.wasm"
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


def test_rust_init_refuses_to_overwrite_existing_project_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Cargo.toml").write_text("user cargo file")
    (tmp_path / "input.wasm").write_bytes(b"wasm")

    def fake_run(command, check, **_kwargs):
        assert check is True
        if command[:4] == ["cargo", "component", "new", "--lib"]:
            staged = Path(command[-1])
            (staged / "src").mkdir(parents=True)
            (staged / "Cargo.toml").write_text("generated")
            (staged / "src" / "lib.rs").write_text("generated")

    monkeypatch.setattr("tarawasm.cli.subprocess.run", fake_run)
    result = CliRunner().invoke(
        cli,
        ["init", "--lang", "rust", "--wasm-file", "input.wasm", "adder"],
    )

    assert result.exit_code != 0
    assert "would overwrite existing path(s): Cargo.toml" in result.output
    assert (tmp_path / "Cargo.toml").read_text() == "user cargo file"
    assert not (tmp_path / "src").exists()
    assert not (tmp_path / "tarawasm.json").exists()


def test_docker_mode_does_not_change_existing_permissions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    protected = tmp_path / "keep.txt"
    protected.write_text("keep")
    protected.chmod(0o640)
    conf = Config("adder", "python", Path("wit"), "main.py", "input.wasm")
    monkeypatch.setattr("tarawasm.cli.Config.load", lambda: conf)

    def fake_run(_command, check, **_kwargs):
        assert check is True
        generated = tmp_path / "wit_world" / "generated.py"
        generated.parent.mkdir()
        generated.write_text("generated")

    monkeypatch.setattr("tarawasm.cli.subprocess.run", fake_run)
    monkeypatch.setenv("INSIDE_DOCKER", "1")

    result = CliRunner().invoke(cli, ["bind"])

    assert result.exit_code == 0
    assert os.stat(protected).st_mode & 0o777 == 0o640

import os
from pathlib import Path

from utils import run_cli


def test_run_cli_docker_adds_platform_when_configured(monkeypatch, tmp_path):
    captured = {}

    monkeypatch.setattr("utils.cli_mode_available", lambda mode: mode == "docker")
    monkeypatch.setenv("TARAWASM_DOCKER_IMAGE", "tarawasm:test")
    monkeypatch.setenv("TARAWASM_DOCKER_PLATFORM", "linux/amd64")

    def fake_run(cmd, check, cwd, env):
        captured["cmd"] = cmd
        captured["check"] = check
        captured["cwd"] = Path(cwd)
        captured["env"] = env

    monkeypatch.setattr("utils.subprocess.run", fake_run)

    run_cli(tmp_path, "build", mode="docker")

    assert captured["check"] is True
    assert captured["cwd"] == Path(tmp_path)
    assert captured["cmd"][:5] == ["docker", "run", "--rm", "--platform", "linux/amd64"]
    assert captured["cmd"][-2:] == ["tarawasm:test", "build"]
    assert os.path.sep in captured["cmd"][captured["cmd"].index("-v") + 1]


def test_run_cli_docker_without_platform_uses_default(monkeypatch, tmp_path):
    captured = {}

    monkeypatch.setattr("utils.cli_mode_available", lambda mode: mode == "docker")
    monkeypatch.setenv("TARAWASM_DOCKER_IMAGE", "tarawasm:test")
    monkeypatch.delenv("TARAWASM_DOCKER_PLATFORM", raising=False)
    monkeypatch.setattr(
        "utils.subprocess.run",
        lambda cmd, check, cwd, env: captured.setdefault("cmd", cmd),
    )

    run_cli(tmp_path, "bind", mode="docker")

    assert "--platform" not in captured["cmd"]

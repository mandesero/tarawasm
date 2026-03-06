import os
from pathlib import Path

from utils import run_cli, run_runtime, run_tool, runtime_available


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


def test_runtime_available_uses_docker_image_in_docker_runtime_mode(monkeypatch):
    monkeypatch.setenv("TARAWASM_RUNTIME_MODE", "docker")
    monkeypatch.setattr("utils.cli_mode_available", lambda mode: mode == "docker")

    assert runtime_available("docker") is True


def test_run_runtime_uses_docker_when_enabled(monkeypatch, tmp_path):
    captured = {}
    wasm_file = tmp_path / "adder.wasm"
    wasm_file.write_text("dummy")

    monkeypatch.setenv("TARAWASM_RUNTIME_MODE", "docker")
    monkeypatch.setenv("TARAWASM_DOCKER_IMAGE", "tarawasm:test")
    monkeypatch.setenv("TARAWASM_DOCKER_PLATFORM", "linux/amd64")
    monkeypatch.setattr("utils.cli_mode_available", lambda mode: mode == "docker")

    def fake_run(cmd, capture_output, text, check):
        captured["cmd"] = cmd
        captured["capture_output"] = capture_output
        captured["text"] = text
        captured["check"] = check
        return type("Result", (), {"stdout": "ok"})()

    monkeypatch.setattr("utils.subprocess.run", fake_run)

    result = run_runtime(tmp_path, wasm_file, mode="docker")

    assert result.stdout == "ok"
    assert captured["cmd"][:5] == ["docker", "run", "--rm", "--platform", "linux/amd64"]
    assert captured["cmd"][-2:] == ["wasmtime", "/work/adder.wasm"]
    assert captured["capture_output"] is True
    assert captured["text"] is True
    assert captured["check"] is True


def test_run_tool_uses_docker_prefix(monkeypatch, tmp_path):
    captured = {}

    monkeypatch.setenv("TARAWASM_DOCKER_IMAGE", "tarawasm:test")
    monkeypatch.setenv("TARAWASM_DOCKER_PLATFORM", "linux/amd64")
    monkeypatch.setattr("utils.cli_mode_available", lambda mode: mode == "docker")

    def fake_run(cmd, check, cwd, capture_output, text):
        captured["cmd"] = cmd
        captured["check"] = check
        captured["cwd"] = Path(cwd)
        captured["capture_output"] = capture_output
        captured["text"] = text
        return type("Result", (), {"stdout": "ok"})()

    monkeypatch.setattr("utils.subprocess.run", fake_run)

    run_tool(
        tmp_path, "wkg", "wit", "build", mode="docker", capture_output=True, text=True
    )

    assert captured["cmd"][:5] == ["docker", "run", "--rm", "--platform", "linux/amd64"]
    assert captured["cmd"][-4:] == ["tarawasm:test", "wkg", "wit", "build"]
    assert captured["check"] is True
    assert captured["cwd"] == Path(tmp_path)
    assert captured["capture_output"] is True
    assert captured["text"] is True

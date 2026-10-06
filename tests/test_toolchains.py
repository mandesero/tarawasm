import json
import os
import subprocess
import tarfile
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from tarawasm.cli import cli
from tarawasm.toolchains import discovery, installer, runtime
from tarawasm.toolchains.catalog import TOOLS, tools_for, version_status
from tarawasm.toolchains.settings import (
    LOCK_FILE,
    ToolchainError,
    read_settings,
    save_profile,
    selected_profile,
    write_settings,
)


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("TARAWASM_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("TARAWASM_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("INSIDE_DOCKER", raising=False)
    monkeypatch.delenv("TARAWASM_TOOLCHAIN_LANGUAGE", raising=False)
    monkeypatch.chdir(tmp_path)


def ready(language, profile=None):
    return {
        "language": language,
        "mode": (profile or {}).get("mode", "local"),
        "ready": True,
        "tools": [
            {
                "tool": name,
                "mode": "local",
                "status": "ready",
                "version": TOOLS[name]["minimum"],
                "supported": "supported",
                "location": "/tools/" + name,
                "detail": "found",
            }
            for name in tools_for(language)
        ],
    }


def test_versions_include_upper_bound():
    assert version_status("go", "1.25.6") == "ready"
    assert version_status("go", "1.24.9") == "outdated"
    assert version_status("go", "1.28.0") == "incompatible"
    assert version_status("tinygo", "0.43.0") == "incompatible"


def test_project_overrides_user_and_lock_constrains_versions(tmp_path):
    save_profile("python", {"mode": "docker", "image": "example:one"})
    save_profile(
        "python", {"mode": "local", "tools": {"wasm-tools": "/tools/wasm"}}, tmp_path
    )
    write_settings(
        tmp_path / LOCK_FILE,
        {
            "schema_version": 1,
            "languages": {
                "python": {
                    "mode": "docker",
                    "image": "example@sha256:123",
                    "versions": {"wasm-tools": "1.245.1"},
                }
            },
        },
    )
    profile, source = selected_profile("python", tmp_path)
    assert profile["mode"] == "local"
    assert "image" not in profile
    assert profile["tools"]["wasm-tools"] == "/tools/wasm"
    assert profile["versions"]["wasm-tools"] == "1.245.1"
    assert source == str(tmp_path / "tarawasm.local.json")


@pytest.mark.parametrize(
    "profile",
    [
        {"mode": "shell"},
        {"mode": "docker", "image": "--privileged"},
        {"mode": "local", "tools": {"node": "relative"}},
        {"mode": "local", "unknown": 1},
    ],
)
def test_invalid_profiles_do_not_write(tmp_path, profile):
    with pytest.raises(ToolchainError):
        save_profile("js", profile, tmp_path)
    assert not (tmp_path / "tarawasm.local.json").exists()


def test_corrupt_settings_are_not_silently_ignored(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("not json")
    with pytest.raises(ToolchainError):
        read_settings(path)


def test_discovery_checks_actual_binary_and_versions(monkeypatch):
    monkeypatch.setattr(discovery.shutil, "which", lambda name, **_kw: "/tools/" + name)
    versions = {
        "python3": "3.10.0",
        "wasm-tools": "1.245.1",
        "wkg": "0.14.0",
        "componentize-py": "0.21.0",
    }
    monkeypatch.setattr(
        discovery,
        "run_probe",
        lambda argv, **_kw: subprocess.CompletedProcess(
            argv, 0, versions[Path(argv[0]).name], ""
        ),
    )
    report = discovery.discover_local("python")
    assert not report["ready"]
    assert (
        next(row for row in report["tools"] if row["tool"] == "wkg")["status"]
        == "outdated"
    )


def test_unknown_version_is_not_missing(monkeypatch):
    monkeypatch.setattr(discovery.shutil, "which", lambda *_a, **_kw: "/tools/tool")
    monkeypatch.setattr(
        discovery,
        "run_probe",
        lambda argv, **_kw: subprocess.CompletedProcess(
            argv, 0, "development build", ""
        ),
    )
    assert {row["status"] for row in discovery.discover_local("python")["tools"]} == {
        "unknown"
    }


def test_docker_status_never_pulls(monkeypatch):
    calls = []
    monkeypatch.setattr(discovery, "docker_available", lambda: (True, "ready"))

    def probe(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1, "", "not found")

    monkeypatch.setattr(discovery, "run_probe", probe)
    report = discovery.discover_docker(
        "python", {"mode": "docker", "image": "example:python"}
    )
    assert report["status"] == "not downloaded"
    assert calls == [["docker", "image", "inspect", "example:python"]]


def test_failed_switch_preserves_selection(monkeypatch):
    save_profile("python", {"mode": "local"})
    monkeypatch.setattr(
        "tarawasm.toolchains.cli.inspect_profile",
        lambda language, profile: {
            "language": language,
            "mode": profile["mode"],
            "tools": [],
            "ready": False,
        },
    )
    result = CliRunner().invoke(cli, ["toolchain", "use", "python", "--mode", "docker"])
    assert result.exit_code == 1
    assert "Selection unchanged" in result.output
    assert selected_profile("python")[0] == {"mode": "local"}


def test_setup_all_docker_plans_only_and_deduplicates_image(monkeypatch):
    monkeypatch.setattr(
        "tarawasm.toolchains.cli.execute",
        lambda *_a: pytest.fail("unexpected installation"),
    )
    result = CliRunner().invoke(
        cli,
        ["toolchain", "setup", "--all", "--mode", "docker", "--image", "example:all"],
    )
    assert result.exit_code == 0, result.output
    assert result.output.count("docker pull") == 1
    assert selected_profile("python")[0] is None


def test_noninteractive_install_requires_yes(monkeypatch):
    monkeypatch.setattr(
        "tarawasm.toolchains.cli.docker_available", lambda: (True, "ready")
    )
    monkeypatch.setattr(
        "tarawasm.toolchains.cli.execute",
        lambda *_a: pytest.fail("unexpected installation"),
    )
    result = CliRunner().invoke(
        cli, ["toolchain", "setup", "python", "--mode", "docker", "--install"]
    )
    assert result.exit_code == 1
    assert "requires --yes" in result.output


def test_setup_requires_mode_without_tty():
    result = CliRunner().invoke(cli, ["toolchain", "setup", "--all"])
    assert result.exit_code == 2
    assert "Specify --mode" in result.output


def test_setup_all_install_checks_every_language(monkeypatch):
    calls = []
    checked = []
    monkeypatch.setattr(
        "tarawasm.toolchains.cli.docker_available", lambda: (True, "ready")
    )
    monkeypatch.setattr(
        "tarawasm.toolchains.cli.execute", lambda argv, _env: calls.append(argv)
    )

    def inspect(language, profile):
        checked.append(language)
        report = ready(language, profile)
        if language == "rust":
            report["ready"] = False
        return report

    monkeypatch.setattr("tarawasm.toolchains.cli.inspect_profile", inspect)
    result = CliRunner().invoke(
        cli, ["toolchain", "setup", "--all", "--mode", "docker", "--install", "--yes"]
    )
    assert result.exit_code == 1
    assert len(calls) == 5
    assert checked == ["python", "go", "js", "rust", "c"]


def test_unsupported_install_platform_fails_before_writes(monkeypatch, tmp_path):
    monkeypatch.setattr(installer.platform, "system", lambda: "Windows")
    with pytest.raises(ToolchainError, match="macOS"):
        installer.install_tools(["go"])
    assert not (tmp_path / "data").exists()


def test_archive_traversal_rejected(tmp_path):
    archive = tmp_path / "bad.tar"
    with tarfile.open(archive, "w") as target:
        member = tarfile.TarInfo("../escape")
        target.addfile(member)
    with pytest.raises(ToolchainError, match="Unsafe"):
        installer.extract_archive(archive, tmp_path / "extract")
    assert not (tmp_path / "escape").exists()


def test_archive_external_symlink_rejected(tmp_path):
    archive = tmp_path / "bad.tar"
    with tarfile.open(archive, "w") as target:
        member = tarfile.TarInfo("link")
        member.type = tarfile.SYMTYPE
        member.linkname = "/etc"
        target.addfile(member)
    with pytest.raises(ToolchainError, match="Unsafe"):
        installer.extract_archive(archive, tmp_path / "extract")


def test_doctor_json_remains_parseable_on_failure(monkeypatch):
    report = ready("python")
    report["ready"] = False
    monkeypatch.setattr("tarawasm.toolchains.cli.report_for", lambda *_a: report)
    result = CliRunner().invoke(cli, ["doctor", "--lang", "python", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.output)["reports"][0]["ready"] is False


def test_first_init_missing_tools_does_not_create_project(monkeypatch, tmp_path):
    wit = tmp_path / "input.wit"
    wit.write_text("world example {}")
    report = ready("python")
    report["ready"] = False
    monkeypatch.setattr(runtime, "discover_local", lambda *_a: report)
    result = CliRunner().invoke(
        cli, ["init", "--lang", "python", "--wit", str(wit), "project"]
    )
    assert result.exit_code == 1
    assert "Toolchain is incomplete" in result.output
    assert not (tmp_path / "project").exists()


def test_help_does_not_probe(monkeypatch):
    monkeypatch.setattr(
        runtime, "discover_local", lambda *_a: pytest.fail("unexpected diagnostic")
    )
    assert CliRunner().invoke(cli, ["--help"]).exit_code == 0
    assert CliRunner().invoke(cli, ["init", "--help"]).exit_code == 0


def test_saved_docker_choice_does_not_switch_to_found_local(monkeypatch, tmp_path):
    wit = tmp_path / "input.wit"
    wit.write_text("world example {}")
    save_profile("python", {"mode": "docker", "image": "example:python"})
    calls = []
    monkeypatch.setattr(runtime, "inspect_profile", ready)
    monkeypatch.setattr(
        runtime.subprocess, "run", lambda argv, **_kw: calls.append(argv)
    )
    result = CliRunner().invoke(
        cli, ["init", "--lang", "python", "--wit", str(wit), "project"]
    )
    assert result.exit_code == 0, result.output
    assert calls[0][0:2] == ["docker", "run"]
    assert "--pull=never" in calls[0]
    assert "--privileged" not in calls[0]
    assert "example:python" in calls[0]
    assert "init" in calls[0]


def test_custom_path_used_without_shell_interpolation(tmp_path):
    profile = {
        "mode": "local",
        "tools": {"wasm-tools": str(tmp_path / "name with spaces; echo bad")},
    }
    token = runtime.ACTIVE.set(profile)
    try:
        assert runtime.executable("wasm-tools") == profile["tools"]["wasm-tools"]
        assert runtime.executable("wkg") == "wkg"
    finally:
        runtime.ACTIVE.reset(token)


def test_inside_container_never_launches_nested_docker(monkeypatch, tmp_path):
    wit = tmp_path / "input.wit"
    wit.write_text("world example {}")
    monkeypatch.setenv("INSIDE_DOCKER", "1")
    result = CliRunner().invoke(
        cli,
        [
            "init",
            "--lang",
            "python",
            "--wit",
            str(wit),
            "--execution",
            "docker",
            "project",
        ],
    )
    assert result.exit_code == 1
    assert "nested Docker" in result.output


def test_environment_restored_after_failed_local_operation(monkeypatch):
    @click.command()
    @click.option("--lang", "language", default="python")
    @runtime.execution_options
    def operation(language):
        assert runtime.ACTIVE.get() is not None
        raise click.ClickException("failure")

    monkeypatch.setattr(runtime, "inspect_profile", ready)
    before = os.environ.copy()
    result = CliRunner().invoke(operation, ["--execution", "local"])
    assert result.exit_code == 1
    assert runtime.ACTIVE.get() is None
    assert os.environ == before


def test_archive_link_then_parent_traversal_rejected(tmp_path):
    archive = tmp_path / "bad.tar"
    with tarfile.open(archive, "w") as target:
        link = tarfile.TarInfo("a")
        link.type, link.linkname = tarfile.SYMTYPE, "."
        target.addfile(link)
        target.addfile(tarfile.TarInfo("a/../escape"))
    with pytest.raises(ToolchainError):
        installer.extract_archive(archive, tmp_path / "extract")
    assert not (tmp_path / "escape").exists()


def test_lock_only_is_marked_for_validation(tmp_path):
    write_settings(
        tmp_path / LOCK_FILE,
        {
            "schema_version": 1,
            "languages": {
                "python": {"mode": "local", "versions": {"wasm-tools": "1.245.1"}}
            },
        },
    )
    profile, source = selected_profile("python", tmp_path)
    assert profile["versions"]
    assert source != "discovery"


def test_setup_preserves_custom_image_and_platform():
    save_profile(
        "python",
        {"mode": "docker", "image": "example:custom", "platform": "linux/arm64"},
    )
    result = CliRunner().invoke(cli, ["toolchain", "setup", "python"])
    assert result.exit_code == 0, result.output
    assert "example:custom" in result.output
    assert "linux/arm64" in result.output
    assert "mandeser0" not in result.output


def test_docker_mode_override_obeys_project_lock(tmp_path):
    write_settings(
        tmp_path / LOCK_FILE,
        {
            "schema_version": 1,
            "languages": {
                "python": {
                    "mode": "docker",
                    "image": "example@sha256:abc",
                    "versions": {},
                }
            },
        },
    )
    profile, _ = selected_profile("python", tmp_path, mode="docker")
    assert profile["image"] == "example@sha256:abc"
    with pytest.raises(ToolchainError, match="differs"):
        selected_profile("python", tmp_path, mode="docker", image="example:new")


def test_custom_cargo_plugin_and_rustc_are_honored(tmp_path):
    profile = {
        "mode": "local",
        "tools": {
            "cargo-component": str(tmp_path / "renamed-plugin"),
            "rustc": str(tmp_path / "renamed-rustc"),
        },
    }
    token = runtime.ACTIVE.set(profile)
    try:
        assert runtime.command_argv(("cargo", "component", "build")) == (
            str(tmp_path / "renamed-plugin"),
            "component",
            "build",
        )
        assert discovery.local_environment(profile)["RUSTC"] == str(
            tmp_path / "renamed-rustc"
        )
    finally:
        runtime.ACTIVE.reset(token)


def test_docker_working_directory_root_is_rejected(monkeypatch):
    monkeypatch.chdir("/")
    context = click.Context(click.Command("strip"))
    with pytest.raises(ToolchainError, match="filesystem root"):
        runtime.docker_command({"mode": "docker"}, "python", context, None)


def test_external_strip_default_output_parent_is_writable(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    wasm = external / "input.wasm"
    wasm.write_bytes(b"wasm")
    monkeypatch.chdir(work)
    context = click.Context(click.Command("strip"))
    context.params = {"wasm": str(wasm)}
    argv = runtime.docker_command({"mode": "docker"}, "python", context, None)
    assert f"type=bind,source={external},target={external}" in argv


def test_root_ci_prerequisites_do_not_require_sudo(monkeypatch):
    monkeypatch.setattr(installer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(installer.os, "getuid", lambda: 0)
    monkeypatch.setattr(installer, "linux_package_manager", lambda: "apt-get")
    assert installer.prerequisites_command()[0] == "apt-get"


def test_local_plan_uses_current_python_interpreter(monkeypatch):
    monkeypatch.setattr(
        "tarawasm.toolchains.cli.prerequisite_commands", lambda _names: []
    )
    monkeypatch.setattr(
        "tarawasm.toolchains.cli.installation_plan", lambda *_a, **_kw: ["wasm-tools"]
    )
    monkeypatch.setattr("tarawasm.toolchains.cli.discover_local", ready)
    monkeypatch.setattr(
        "tarawasm.toolchains.cli.sys.executable", "/tmp/python with spaces"
    )
    result = CliRunner().invoke(
        cli, ["toolchain", "setup", "python", "--mode", "local"]
    )
    assert result.exit_code == 0, result.output
    assert (
        "'/tmp/python with spaces' -m tarawasm.cli toolchain setup python --mode local --install --yes"
        in result.output
    )


def test_jco_uses_metadata_of_selected_executable(tmp_path, monkeypatch):
    package = tmp_path / "jco"
    (package / "src").mkdir(parents=True)
    (package / "package.json").write_text(
        json.dumps({"name": "@bytecodealliance/jco", "version": "1.37.0"})
    )
    binary = package / "src/jco.js"
    binary.write_text("script")
    monkeypatch.setattr(
        discovery.shutil,
        "which",
        lambda name, **_kw: str(binary) if name == "jco" else None,
    )
    monkeypatch.setattr(
        discovery,
        "run_probe",
        lambda argv, **_kw: subprocess.CompletedProcess(argv, 0, "1.16.1", ""),
    )
    row = next(
        row for row in discovery.discover_local("js")["tools"] if row["tool"] == "jco"
    )
    assert row["version"] == "1.37.0"
    assert row["status"] == "ready"


def test_wasi_sdk_distribution_version_suffix(tmp_path, monkeypatch):
    sdk = tmp_path / "sdk"
    (sdk / "share/wasi-sysroot").mkdir(parents=True)
    monkeypatch.setenv("WASI_SDK_PATH", str(sdk))
    monkeypatch.setattr(
        discovery.shutil,
        "which",
        lambda name, **_kw: "/tools/clang" if name == "clang" else None,
    )
    monkeypatch.setattr(
        discovery,
        "run_probe",
        lambda argv, **_kw: subprocess.CompletedProcess(
            argv, 0, "clang version 21.1.8-wasi-sdk\nTarget: wasm32-unknown-wasi\n", ""
        ),
    )
    row = next(
        row for row in discovery.discover_local("c")["tools"] if row["tool"] == "clang"
    )
    assert row["version"] == "21.1.8"
    assert row["status"] == "ready"


@pytest.mark.parametrize("mode", ["local", "docker"])
def test_project_switch_respects_lock_and_preserves_selection(
    tmp_path, monkeypatch, mode
):
    monkeypatch.setattr("tarawasm.toolchains.cli.project_root", lambda: tmp_path)
    save_profile("python", {"mode": "local"}, tmp_path)
    write_settings(
        tmp_path / LOCK_FILE,
        {
            "schema_version": 1,
            "languages": {
                "python": {
                    "mode": "docker",
                    "image": "example@sha256:abc",
                    "versions": {"wasm-tools": "1.245.1"},
                }
            },
        },
    )
    original = (tmp_path / "tarawasm.local.json").read_bytes()

    def inspect(language, profile):
        assert profile["versions"] == {"wasm-tools": "1.245.1"}
        return {"language": language, "mode": mode, "ready": False, "tools": []}

    monkeypatch.setattr("tarawasm.toolchains.cli.inspect_profile", inspect)
    arguments = ["toolchain", "use", "python", "--project", "--mode", mode]
    if mode == "docker":
        arguments.extend(["--image", "example:new"])
    result = CliRunner().invoke(cli, arguments)
    assert result.exit_code == 1
    assert (tmp_path / "tarawasm.local.json").read_bytes() == original
    assert (
        "differs from the project lock" if mode == "docker" else "Selection unchanged"
    ) in result.output


@pytest.mark.parametrize("constraint", ["versions", "tools"])
def test_all_install_plan_validates_each_language_before_dedup(monkeypatch, constraint):
    monkeypatch.setattr(installer, "supported_host", lambda: None)

    def report(language, profile):
        value = ready(language, profile)
        if language == "python":
            next(row for row in value["tools"] if row["tool"] == "wasm-tools")[
                "status"
            ] = "incompatible"
        return value

    monkeypatch.setattr(installer, "discover_local", report)
    profiles = {
        "python": {
            "mode": "local",
            constraint: {
                "wasm-tools": "1.240.0" if constraint == "versions" else "/custom/wasm"
            },
        }
    }
    with pytest.raises(ToolchainError, match="Locked|Selected binary"):
        installer.installation_plan(["python", "c"], upgrade=True, profiles=profiles)
    with pytest.raises(ToolchainError, match="need attention"):
        installer.installation_plan(["python", "c"], profiles=profiles)


def test_custom_node_routes_env_shebang_and_removes_alias(tmp_path):
    binary = tmp_path / "node24"
    binary.write_text("#!/bin/sh\nprintf selected-node\\n\n")
    binary.chmod(0o755)
    jco = tmp_path / "jco"
    jco.write_text("#!/usr/bin/env node\nignored input\n")
    jco.chmod(0o755)
    with discovery.local_execution_environment(
        {"mode": "local", "tools": {"node": str(binary)}}
    ) as env:
        alias = Path(env["PATH"].split(os.pathsep)[0])
        assert subprocess.check_output([str(jco)], env=env, text=True).startswith(
            "selected-node"
        )
    assert not alias.exists()


@pytest.mark.parametrize("fail", [False, True])
def test_component_publication_stages_on_destination_filesystem(
    tmp_path, monkeypatch, fail
):
    from tarawasm.cli import _publish_component

    source = tmp_path / "build/component.wasm"
    source.parent.mkdir()
    source.write_bytes(b"new validated component")
    output = tmp_path / "output/component.wasm"
    output.parent.mkdir()
    output.write_bytes(b"previous successful component")
    replace = os.replace

    def replace_on_device(staged, destination):
        assert Path(staged).parent == output.parent
        if fail:
            raise OSError("simulated publication failure")
        replace(staged, destination)

    monkeypatch.setattr(os, "replace", replace_on_device)
    if fail:
        with pytest.raises(OSError, match="publication failure"):
            _publish_component(source, output)
        assert output.read_bytes() == b"previous successful component"
        assert source.exists()
    else:
        _publish_component(source, output)
        assert output.read_bytes() == b"new validated component"
        assert not source.exists()
    assert list(output.parent.iterdir()) == [output]


def test_js_docker_identity_is_readonly_and_operation_local(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime.os, "getuid", lambda: 12345)
    monkeypatch.setattr(runtime.os, "getgid", lambda: 23456)
    command = click.Command("build")
    with runtime.docker_user_file("js") as identity:
        assert (
            "tarawasm-user:x:12345:23456:tarawasm:/tmp/tarawasm-home:"
            in identity.read_text()
        )
        context = click.Context(command)
        args = runtime.docker_command(
            {"mode": "docker", "image": "example:js"},
            "js",
            context,
            tmp_path,
            identity=identity,
        )
        assert args[args.index("--user") + 1] == "12345:23456"
        assert f"type=bind,source={identity},target=/etc/passwd,readonly" in args
        assert "--privileged" not in args
    assert not identity.exists()
    with runtime.docker_user_file("python") as identity:
        assert identity is None


def test_tinygo_without_optimizer_is_not_ready(tmp_path, monkeypatch):
    binary = tmp_path / "tinygo"
    binary.write_text('#!/bin/sh\necho "tinygo version 0.42.0"\n')
    binary.chmod(0o755)
    monkeypatch.setattr(
        discovery, "managed_environment", lambda: {"PATH": str(tmp_path)}
    )
    report = discovery.discover_local(
        "go", {"mode": "local", "tools": {"tinygo": str(binary)}}
    )
    row = next(row for row in report["tools"] if row["tool"] == "tinygo")
    assert row["status"] == "missing"
    assert "wasm-opt" in row["detail"]


def test_js_reports_dependency_resolved_by_selected_jco(tmp_path, monkeypatch):
    prefix = tmp_path / "npm"
    jco = prefix / "node_modules/@bytecodealliance/jco/src/jco.js"
    jco.parent.mkdir(parents=True)
    jco.write_text("")
    component = jco.parent.parent / "node_modules/@bytecodealliance/componentize-js"
    shim = component / "node_modules/@bytecodealliance/preview2-shim"
    shim.mkdir(parents=True)
    (component / "package.json").write_text(json.dumps({"version": "0.19.3"}))
    (shim / "package.json").write_text(json.dumps({"version": "0.29.0"}))
    monkeypatch.setattr(discovery, "managed_environment", lambda: {"PATH": ""})
    report = discovery.discover_local(
        "js", {"mode": "local", "tools": {"jco": str(jco)}}
    )
    row = next(row for row in report["tools"] if row["tool"] == "preview2-shim")
    assert row["version"] == "0.29.0"
    assert row["status"] == "incompatible"
    assert row["location"] == str(shim / "package.json")


@pytest.mark.parametrize(
    "version,status", [("0.28.0", "incompatible"), ("0.17.8", "ready")]
)
def test_js_checks_legacy_componentizer_shim(tmp_path, monkeypatch, version, status):
    package = tmp_path / "node_modules/@bytecodealliance/jco"
    jco = package / "src/jco.js"
    jco.parent.mkdir(parents=True)
    jco.write_text("")
    (package / "package.json").write_text(
        json.dumps({"name": "@bytecodealliance/jco", "version": "1.37.0"})
    )
    for name, shim_version in [
        ("@bytecodealliance/componentize-js", "0.17.8"),
        ("componentize-js-0-19-3", version),
    ]:
        component = package / "node_modules" / name
        shim = component / "node_modules/@bytecodealliance/preview2-shim"
        shim.mkdir(parents=True)
        (component / "package.json").write_text(json.dumps({"version": "0.23.0"}))
        (shim / "package.json").write_text(json.dumps({"version": shim_version}))
    monkeypatch.setattr(discovery, "managed_environment", lambda: {"PATH": ""})
    report = discovery.discover_local(
        "js", {"mode": "local", "tools": {"jco": str(jco)}}
    )
    row = next(row for row in report["tools"] if row["tool"] == "preview2-shim")
    assert row["status"] == status
    if status != "ready":
        assert "legacy" in row["detail"]


@pytest.mark.parametrize(
    "action,dry_run,writable",
    [
        ("resolve", False, True),
        ("update", False, True),
        ("resolve", True, False),
        ("list", False, False),
    ],
)
def test_external_wit_docker_mount_permissions(
    tmp_path, monkeypatch, action, dry_run, writable
):
    import click

    root = tmp_path / "project"
    root.mkdir()
    wit = tmp_path / "external-wit"
    wit.mkdir()
    (root / "tarawasm.json").write_text(
        json.dumps(
            {
                "language": "python",
                "world": "calculator",
                "wit": {"path": str(wit), "package": "example:calculator"},
                "source": "src",
                "output": "dist/component.wasm",
            }
        )
    )
    monkeypatch.chdir(root)
    parent = click.Context(click.Command("deps"), info_name="deps")
    context = click.Context(click.Command(action), parent=parent, info_name=action)
    context.params = {"dry_run": dry_run}
    args = runtime.docker_command({"mode": "docker"}, "python", context, root)
    expected = f"type=bind,source={wit},target={wit}" + (
        "" if writable else ",readonly"
    )
    assert expected in args

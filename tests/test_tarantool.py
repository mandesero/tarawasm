"""Installation safety and contracts, independent of network/compiler availability."""

import copy
import hashlib
import io
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from tarawasm import tarantool
from tarawasm.backends.base import BackendError, Command
from tarawasm.cli import cli
from tarawasm.config import SUPPORTED_LANGUAGES, Config


def tar_bytes(files):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return output.getvalue()


def zip_bytes(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


@pytest.fixture
def release(monkeypatch, tmp_path):
    monkeypatch.setenv("INSIDE_DOCKER", "1")
    monkeypatch.setenv("TARAWASM_TOOLCHAIN_LANGUAGE", "all")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        tarantool, "tool_requirements", lambda language, version=None: None
    )
    monkeypatch.setattr(tarantool, "_run", lambda *args: None)
    for suffix in ("macos-arm64.dylib", "linux-x86_64.so"):
        monkeypatch.setitem(
            tarantool.release()["checksums"],
            suffix,
            hashlib.sha256(suffix.encode()).hexdigest(),
        )
    monkeypatch.setattr(
        "tarawasm.backends.csharp.CSharpBackend.initialize_files",
        lambda *args: {
            Path("Component.csproj"): "<Project><ItemGroup></ItemGroup></Project>",
            Path("nuget.config"): "<configuration><clear /></configuration>",
            Path("src/App.cs"): "throw new NotImplementedException();",
        },
    )
    packages = {
        "python": (
            "sdk.whl",
            zip_bytes(
                {
                    "_tarantool.py": b"# raw imports\n",
                    "twr_python_sdk/__init__.py": b"",
                    "twr_python_sdk/_guest/patch_wasi_socket_errors.py": b"from pathlib import Path\n",
                }
            ),
        ),
        "js": (
            "sdk.tgz",
            tar_bytes({"package/src/index.js": b"export const box = {};\n"}),
        ),
        "go": (
            "sdk.tar.gz",
            tar_bytes(
                {"sdk/go.mod": f"module {tarantool.release()['go_module']}\n".encode()}
            ),
        ),
        "rust": (
            "sdk.crate",
            tar_bytes(
                {
                    "sdk/Cargo.toml": b"[package]\nname='tarantool-wasm'\nversion='0.1.0'\n"
                }
            ),
        ),
        "csharp": ("Tarantool.Wasm.0.1.0.nupkg", b"nuget package"),
    }
    contents = {}
    prefix = f"tarantool-wasm-{tarantool.CATALOG['default']}-sdk"
    for language, (name, data) in packages.items():
        contents[f"{prefix}/packages/{language}/{name}"] = data
        contents[
            f"{prefix}/wit/{language}/deps/tarantool/package.wit"
        ] = b"""package tarantool:tarantool@0.2.0;
interface database { schema-version: func() -> u32; }
world guest { import database; }
"""
        if language == "python":
            contents[f"{prefix}/wit/python/deps/adder/package.wit"] = (
                b"package docs:adder@0.1.3; interface ssl-bio {}"
            )
        if language == "go":
            contents[f"{prefix}/wit/go/deps/cli/package.wit"] = (
                b"package wasi:cli@0.2.12; world imports {}"
            )
    calls = []

    def asset(suffix, destination, version):
        calls.append((version, suffix))
        destination.write_bytes(
            tar_bytes(
                {
                    name.replace(prefix, f"tarantool-wasm-{version}-sdk", 1): data
                    for name, data in contents.items()
                }
            )
            if suffix == "sdk.tar.gz"
            else suffix.encode()
        )

    monkeypatch.setattr(tarantool, "_asset", asset)
    msgpack = tar_bytes(
        {"msgpack-1.0.3/msgpack/__init__.py": b"", "msgpack-1.0.3/COPYING": b"license"}
    )
    monkeypatch.setattr(
        tarantool, "download", lambda url, path, checksum: path.write_bytes(msgpack)
    )
    return calls


def initialize(language="python", *args):
    return CliRunner().invoke(
        cli,
        [
            "init",
            "--target",
            "tarantool",
            "--lang",
            language,
            "--runtime-platform",
            "macos-arm64",
            *args,
            "app",
        ],
    )


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_target_initializes_project_local_inputs(release, tmp_path, language):
    result = initialize(language)
    assert result.exit_code == 0, result.output
    root = tmp_path / "app"
    conf = Config.load(root)
    assert conf.wit_path == Path("wit")
    assert conf.resolve_path(conf.source).is_file()
    assert (root / tarantool.RUNTIME).read_bytes() == b"macos-arm64.dylib"
    assert tarantool.locked_files(conf)["language"] == language
    assert not (root / "run.lua").exists()
    world = tarantool.WitParser().parse(root / "wit").select_world("app")
    assert not world.exports
    assert "create-user" not in (root / conf.source).read_text()


def test_custom_wit_keeps_user_exports_and_bundled_imports(release, tmp_path):
    source = tmp_path / "user.wit"
    content = """package example:users@0.1.0;
interface users { record user { id: u32, name: string } get: func(id: u32) -> option<user>; }
world service { include tarantool:tarantool/guest@0.2.0; export users; }
"""
    source.write_text(content)
    result = initialize("python", "--wit", str(source), "--world", "service")
    assert result.exit_code == 0, result.output
    conf = Config.load(tmp_path / "app")
    assert conf.world == "service"
    assert (conf.project_root / "wit/user.wit").read_text() == content
    assert source.read_text() == content
    assert "class Users" in (conf.project_root / "main.py").read_text()


def test_invalid_custom_wit_never_publishes_project(release, tmp_path):
    source = tmp_path / "invalid.wit"
    source.write_text("this is not WIT")
    result = initialize("python", "--wit", str(source))
    assert result.exit_code != 0
    assert not (tmp_path / "app").exists()


def test_setup_is_idempotent_and_restores_sdk_without_touching_application(
    release, tmp_path, monkeypatch
):
    assert initialize().exit_code == 0
    root = tmp_path / "app"
    monkeypatch.chdir(root)
    (root / "main.py").write_text("# user implementation\n")
    (root / "wit/app.wit").write_text("# user contract\n")
    before = len(release)
    result = CliRunner().invoke(
        cli, ["tarantool", "setup", "--runtime-platform", "macos-arm64"]
    )
    assert result.exit_code == 0, result.output
    assert len(release) == before
    raw = root / tarantool.SDK / "python/_tarantool.py"
    raw.unlink()
    result = CliRunner().invoke(
        cli, ["tarantool", "setup", "--runtime-platform", "macos-arm64"]
    )
    assert result.exit_code == 0, result.output
    assert raw.read_bytes() == b"# raw imports\n"
    assert (root / "main.py").read_text() == "# user implementation\n"
    assert (root / "wit/app.wit").read_text() == "# user contract\n"


def test_modified_sdk_is_preserved_and_rejected(release, tmp_path, monkeypatch):
    assert initialize().exit_code == 0
    root = tmp_path / "app"
    raw = root / tarantool.SDK / "python/_tarantool.py"
    raw.write_bytes(b"user modification")
    monkeypatch.chdir(root)
    result = CliRunner().invoke(
        cli, ["tarantool", "setup", "--runtime-platform", "macos-arm64"]
    )
    assert result.exit_code == 1 and "Refusing to replace modified" in result.output
    assert raw.read_bytes() == b"user modification"
    with pytest.raises(BackendError, match="Missing or modified"):
        tarantool.build_args(Config.load(root), [])


def test_clean_preserves_runtime_sdk_and_locks(release, tmp_path, monkeypatch):
    assert initialize().exit_code == 0
    root = tmp_path / "app"
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    monkeypatch.chdir(root)
    assert CliRunner().invoke(cli, ["clean"]).exit_code == 0
    assert all(path.read_bytes() == content for path, content in before.items())


def test_symlinked_installation_directory_is_rejected(release, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "app"
    root.mkdir()
    (root / ".rocks").symlink_to(outside, target_is_directory=True)
    result = initialize()
    assert result.exit_code == 1 and "symlinked" in result.output
    assert not list(outside.iterdir())
    assert not (root / "tarawasm.json").exists()


def test_failed_runtime_upgrade_restores_previous_library_and_lock(
    release, tmp_path, monkeypatch
):
    assert initialize().exit_code == 0
    root = tmp_path / "app"
    previous = (root / tarantool.LOCK).read_bytes()
    monkeypatch.chdir(root)
    import os

    replace = os.replace

    def fail(source, destination):
        if Path(destination) == root / tarantool.LOCK and "new" in Path(source).parts:
            raise OSError("simulated publication failure")
        replace(source, destination)

    monkeypatch.setattr("tarawasm.cli.os.replace", fail)
    result = CliRunner().invoke(
        cli, ["tarantool", "setup", "--runtime-platform", "linux-x86_64", "--upgrade"]
    )
    assert result.exit_code == 1, result.output
    assert (root / tarantool.RUNTIME).read_bytes() == b"macos-arm64.dylib"
    assert (root / tarantool.LOCK).read_bytes() == previous


def test_sdk_only_and_dry_run(release, tmp_path):
    result = initialize("python", "--dry-run")
    assert result.exit_code == 0 and not release
    assert not (tmp_path / "app").exists()
    result = initialize("python", "--sdk-only")
    assert result.exit_code == 0, result.output
    assert not (tmp_path / "app" / tarantool.RUNTIME).exists()


def test_failed_dependency_resolution_never_publishes_project(
    release, tmp_path, monkeypatch
):
    def fail(*args):
        raise subprocess.CalledProcessError(7, ["cargo", "generate-lockfile"])

    monkeypatch.setattr(tarantool, "_run", fail)
    result = initialize("rust")
    assert result.exit_code == 1 and not (tmp_path / "app").exists()


def test_build_profiles_and_sdk_minimum(release, tmp_path, monkeypatch):
    assert initialize("go").exit_code == 0
    conf = Config.load(tmp_path / "app")
    assert tarantool.build_args(conf, ["-opt=2"]) == [
        "-scheduler=none",
        "-panic-unwind=explicit",
        "-opt=2",
    ]
    with pytest.raises(BackendError, match="manages"):
        tarantool.build_args(conf, ["-scheduler=asyncify"])
    commands = (Command(("go", "get")), Command(("go", "tool", "wit-bindgen-go")))
    bound = tarantool.bind_commands(conf, commands)
    assert [command.argv for command in bound] == [commands[-1].argv]
    assert bound[0].env["GOFLAGS"] == "-mod=readonly"


@pytest.mark.parametrize("payload", [[], {"schema_version": 2}, {"version": "latest"}])
def test_malformed_lock_is_rejected(release, tmp_path, payload):
    assert initialize().exit_code == 0
    root = tmp_path / "app"
    (root / tarantool.LOCK).write_text(json.dumps(payload))
    with pytest.raises(BackendError, match="lock"):
        tarantool.locked_files(Config.load(root))


def test_unzip_rejects_traversal(tmp_path):
    archive = tmp_path / "bad.whl"
    archive.write_bytes(zip_bytes({"../outside": b"unsafe"}))
    with pytest.raises(BackendError, match="Unsafe"):
        tarantool._unzip(archive, tmp_path / "unpacked")
    assert not (tmp_path / "outside").exists()


def test_release_download_is_pinned(monkeypatch, tmp_path):
    captured = []
    monkeypatch.setattr(tarantool, "download", lambda *args: captured.append(args))
    tarantool._asset("sdk.tar.gz", tmp_path / "sdk", "0.1.0")
    url, _, checksum = captured[0]
    assert "/v0.1.0/tarantool-wasm-0.1.0-sdk.tar.gz" in url
    assert checksum == tarantool.release("0.1.0")["checksums"]["sdk.tar.gz"]
    assert len(checksum) == hashlib.sha256().digest_size * 2


@pytest.mark.parametrize("sdk_only", [False, True])
def test_plain_setup_preserves_locked_platform(
    release, tmp_path, monkeypatch, sdk_only
):
    assert initialize("python", *(["--sdk-only"] if sdk_only else [])).exit_code == 0
    root = tmp_path / "app"
    before = (root / tarantool.LOCK).read_bytes()
    monkeypatch.chdir(root)
    monkeypatch.setattr(tarantool.platform, "system", lambda: "Linux")
    monkeypatch.setattr(tarantool.platform, "machine", lambda: "x86_64")
    result = CliRunner().invoke(cli, ["tarantool", "setup"])
    assert result.exit_code == 0, result.output
    assert (root / tarantool.LOCK).read_bytes() == before


@pytest.mark.parametrize("language", ["python", "rust"])
def test_custom_dependency_layout_is_preserved(release, tmp_path, language):
    wit = tmp_path / "input"
    (wit / "deps/obj").mkdir(parents=True)
    (wit / "deps/obj/api.wit").write_text(
        "package example:host@0.1.0; interface api { ping: func(); }"
    )
    (wit / "app.wit").write_text(
        "package example:app@0.1.0; world app { import example:host/api@0.1.0; export ping: func(); }"
    )
    result = initialize(language, "--wit", str(wit), "--world", "app")
    assert result.exit_code == 0, result.output
    root = tmp_path / "app"
    assert (root / "wit/deps/obj/api.wit").is_file()
    tarantool.WitParser().parse(root / "wit").select_world("app")
    if language == "rust":
        assert (
            '"example:host" = { path = "wit/deps/obj" }'
            in (root / "Cargo.toml").read_text()
        )


def test_runtime_lock_requires_managed_artifact(release, tmp_path):
    assert initialize().exit_code == 0
    root = tmp_path / "app"
    data = json.loads((root / tarantool.LOCK).read_text())
    del data["files"][str(tarantool.RUNTIME)]
    (root / tarantool.LOCK).write_text(json.dumps(data))
    with pytest.raises(BackendError, match="runtime lock"):
        tarantool.locked_files(Config.load(root))


@pytest.mark.parametrize("version,accepted", [("0.42.0", False), ("0.43.0", True)])
def test_sdk_minimum_parses_prefixed_version_output(monkeypatch, version, accepted):
    monkeypatch.setattr(
        tarantool.subprocess,
        "check_output",
        lambda *args, **kwargs: f"tinygo version {version} darwin/arm64",
    )
    if accepted:
        tarantool.tool_requirements("go")
    else:
        with pytest.raises(BackendError, match="tinygo >= 0.43.0"):
            tarantool.tool_requirements("go")


@pytest.mark.parametrize("name", ["go.mod", "go.sum"])
def test_implicit_dependency_change_preserves_locks_and_previous_output(
    release, tmp_path, monkeypatch, name
):
    assert initialize("go").exit_code == 0
    root = tmp_path / "app"
    (root / "go.sum").write_text("locked checksums\n")
    original = (root / name).read_bytes()
    output = root / "dist/app.wasm"
    output.parent.mkdir()
    output.write_bytes(b"previous successful component")
    monkeypatch.chdir(root)

    class Backend:
        def validate_world(self, world):
            pass

        def build_command(self, conf, *, output, **kwargs):
            return Command(("compiler", str(output)))

        def finish_build_command(self, *args, **kwargs):
            return None

        def locate_artifact(self, conf, requested):
            return requested

    def compile(command, **kwargs):
        assert command.env["GOFLAGS"] == "-mod=readonly"
        Path(command.argv[1]).write_bytes(b"new component")
        (root / name).write_bytes(b"implicit dependency update")

    monkeypatch.setattr("tarawasm.cli.get_backend", lambda _: Backend())
    monkeypatch.setattr("tarawasm.cli._run", compile)
    monkeypatch.setattr("tarawasm.cli._parse_selected_world", lambda *args: object())
    monkeypatch.setattr("tarawasm.cli.WitParser.parse", lambda *args: object())
    result = CliRunner().invoke(cli, ["build"])
    assert result.exit_code == 1 and "were restored" in result.output
    assert (root / name).read_bytes() == original
    assert output.read_bytes() == b"previous successful component"


def test_reinitialization_does_not_ignore_a_different_wit(release, tmp_path):
    assert initialize().exit_code == 0
    source = tmp_path / "other.wit"
    source.write_text(
        "package example:other@0.1.0; world other { export ping: func(); }"
    )
    before = (tmp_path / "app/wit/app.wit").read_bytes()
    result = initialize("python", "--wit", str(source), "--world", "other")
    assert result.exit_code == 1
    assert (tmp_path / "app/wit/app.wit").read_bytes() == before


def test_rust_local_wit_needs_no_component_registry_lock(release, tmp_path):
    assert initialize("rust").exit_code == 0
    root = tmp_path / "app"
    (root / "Cargo.lock").write_bytes(b"cargo dependencies")
    conf = Config.load(root)
    with tarantool.dependency_locks(conf):
        pass
    with pytest.raises(BackendError, match="were restored"):
        with tarantool.dependency_locks(conf):
            (root / "Cargo-component.lock").write_bytes(b"implicit new registry pin")
    assert not (root / "Cargo-component.lock").exists()
    assert (root / "Cargo.lock").read_bytes() == b"cargo dependencies"


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_generated_identity_and_empty_world(release, tmp_path, language):
    result = initialize(
        language, "--package", "acme:orders@1.2.3", "--world", "user-service"
    )
    assert result.exit_code == 0, result.output
    conf = Config.load(tmp_path / "app")
    assert conf.wit_package == "acme:orders@1.2.3"
    assert conf.world == "user-service"
    assert conf.output == Path("dist/user-service.wasm")
    assert (
        not tarantool.WitParser()
        .parse(tmp_path / "app/wit")
        .select_world(conf.world)
        .exports
    )


@pytest.mark.parametrize(
    "args",
    [
        ("--package", "bad package"),
        ("--package", ""),
        ("--world", ""),
        ("--world", "bad world"),
        ("--package", "acme:orders; world injected {}"),
    ],
)
def test_invalid_generated_identity_precedes_downloads(release, tmp_path, args):
    result = initialize("python", *args)
    assert result.exit_code != 0
    assert not release and not (tmp_path / "app").exists()


def test_package_does_not_relabel_supplied_wit(release, tmp_path):
    wit = tmp_path / "input.wit"
    wit.write_text("package acme:input; world app {}")
    result = initialize("python", "--wit", str(wit), "--package", "acme:other")
    assert result.exit_code != 0 and "without --wit" in result.output
    assert not release


def test_catalog_default_does_not_change_existing_project(
    release, tmp_path, monkeypatch
):
    old_version = tarantool.CATALOG["default"]
    assert initialize("go").exit_code == 0
    root = tmp_path / "app"
    conf = Config.load(root)
    before = (root / tarantool.LOCK).read_bytes()
    newer = copy.deepcopy(tarantool.release(old_version))
    newer["minimum_tools"]["go"] = ["tinygo", "9.0.0"]
    newer["checksums"]["sdk.tar.gz"] = "1" * 64
    monkeypatch.setitem(tarantool.CATALOG["releases"], "0.2.0", newer)
    monkeypatch.setitem(tarantool.CATALOG, "default", "0.2.0")
    versions = []
    monkeypatch.setattr(
        tarantool,
        "tool_requirements",
        lambda language, version: versions.append(version),
    )
    tarantool.build_args(conf, [])
    assert versions == [old_version]
    report = {"tools": [{"tool": "tinygo", "version": "0.43.0"}], "ready": True}
    tarantool.inspect_inputs(conf, report)
    assert report["ready"] and report["tools"][-1]["version"] == old_version
    (root / tarantool.SDK / "go/go.mod").unlink()
    release.clear()
    monkeypatch.chdir(root)
    result = CliRunner().invoke(cli, ["tarantool", "setup"])
    assert result.exit_code == 0, result.output
    assert release and all(version == old_version for version, _ in release)
    assert (root / tarantool.LOCK).read_bytes() == before
    invalid = json.loads(before)
    invalid["version"] = ""
    (root / tarantool.LOCK).write_text(json.dumps(invalid))
    with pytest.raises(BackendError, match="No verified"):
        tarantool.locked_files(conf)
    (root / tarantool.LOCK).write_bytes(before)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli, ["init", "--target", "tarantool", "--lang", "go", "--sdk-only", "new"]
    )
    assert result.exit_code == 0, result.output
    new = Config.load(tmp_path / "new")
    assert tarantool.locked_files(new)["version"] == "0.2.0"
    assert f"v{newer['go_version']}" in (tmp_path / "new/go.mod").read_text()
    result = CliRunner().invoke(
        cli,
        [
            "init",
            "--target",
            "tarantool",
            "--lang",
            "go",
            "--tarantool-wasm-version",
            old_version,
            "--sdk-only",
            "explicit",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (
        tarantool.locked_files(Config.load(tmp_path / "explicit"))["version"]
        == old_version
    )


@pytest.mark.parametrize("version", ["99.0.0", ""])
def test_unknown_release_is_rejected_without_download(release, tmp_path, version):
    result = initialize("python", "--tarantool-wasm-version", version)
    assert result.exit_code != 0 and "No verified" in result.output
    assert not release and not (tmp_path / "app").exists()
    assert initialize().exit_code == 0
    path = tmp_path / "app" / tarantool.LOCK
    data = json.loads(path.read_text())
    data["version"] = version
    path.write_text(json.dumps(data))
    with pytest.raises(BackendError, match="No verified"):
        tarantool.locked_files(Config.load(tmp_path / "app"))


def test_python_initializes_ssl_and_asyncio_dns_without_application_exports(
    release, tmp_path
):
    assert initialize().exit_code == 0
    root = tmp_path / "app"
    source = (root / "main.py").read_text()
    assert "twr_python_sdk.install(ports=['ssl', 'asyncio_dns'])" in source
    assert source.index("twr_python_sdk.install") < source.index("import wit_world")
    world = tarantool.WitParser().parse(root / "wit").select_world("app")
    assert not world.exports
    assert any(
        item.interface and item.interface.name == "ssl-bio" for item in world.imports
    )


def test_supplied_python_wit_preserves_contract_and_enables_requested_ssl(
    release, tmp_path
):
    source = tmp_path / "input.wit"
    text = "package acme:custom; world custom { import docs:adder/ssl-bio@0.1.3; }"
    source.write_text(text)
    result = initialize("python", "--wit", str(source), "--world", "custom")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "app/wit/input.wit").read_text() == text
    assert "twr_python_sdk.install" in (tmp_path / "app/main.py").read_text()


def test_python_postprocessing_follows_locked_release(release, tmp_path, monkeypatch):
    assert initialize().exit_code == 0
    conf = Config.load(tmp_path / "app")
    newer = copy.deepcopy(tarantool.release())
    newer["python"]["patch_socket_errors"] = None
    monkeypatch.setitem(tarantool.CATALOG["releases"], "0.2.0", newer)
    monkeypatch.setitem(tarantool.CATALOG, "default", "0.2.0")
    commands = tarantool.postprocess_commands(conf, tmp_path / "staged.wasm")
    assert len(commands) == 2
    assert commands[0].argv[:3] == ("wasm-tools", "strip", "--all")
    assert commands[1].argv[:3] == ("python3", "-I", "-B")
    assert commands[1].argv[-2] == str(
        conf.project_root
        / tarantool.SDK
        / "python"
        / tarantool.release("0.1.0")["python"]["patch_socket_errors"]
    )


@pytest.mark.parametrize("failure", ["wasm-tools", "python3", None])
def test_python_postprocess_failure_and_dry_run_preserve_output(
    release, tmp_path, monkeypatch, failure
):
    assert initialize().exit_code == 0
    root = tmp_path / "app"
    conf = Config.load(root)
    output = root / conf.output
    output.parent.mkdir()
    output.write_bytes(b"previous successful component")
    monkeypatch.chdir(root)

    class Backend:
        def validate_world(self, world):
            pass

        def build_command(self, conf, *, output, **kwargs):
            return Command(("compiler", str(output)))

        def finish_build_command(self, *args, **kwargs):
            return None

        def locate_artifact(self, conf, requested):
            return requested

    calls = []

    def run(command, *, dry_run=False, **kwargs):
        calls.append(command.argv[0])
        if dry_run:
            return
        if command.argv[0] == "compiler":
            Path(command.argv[1]).write_bytes(b"new unpatched component")
        if command.argv[0] == failure:
            raise BackendError("SDK postprocessing rejected staged output")

    monkeypatch.setattr("tarawasm.cli.get_backend", lambda _: Backend())
    monkeypatch.setattr("tarawasm.cli._run", run)
    result = CliRunner().invoke(
        cli, ["build", *(["--dry-run"] if failure is None else [])]
    )
    assert result.exit_code == (0 if failure is None else 1), result.output
    assert output.read_bytes() == b"previous successful component"
    assert calls == (
        ["compiler", "wasm-tools"]
        if failure == "wasm-tools"
        else ["compiler", "wasm-tools", "python3"]
    )
    if failure is None:
        assert not (conf.build_dir / "publish/app.wasm").exists()


def test_supplied_python_wit_rejects_aliased_ssl_import(release, tmp_path):
    source = tmp_path / "input.wit"
    source.write_text(
        "package acme:custom; world custom { import tls: docs:adder/ssl-bio@0.1.3; }"
    )
    result = initialize("python", "--wit", str(source), "--world", "custom")
    assert result.exit_code == 1 and "SSL import name" in result.output
    assert not (tmp_path / "app").exists()


def test_sdk_socket_script_isolated_from_unlisted_modules(release, tmp_path):
    assert initialize().exit_code == 0
    conf = Config.load(tmp_path / "app")
    sdk = conf.project_root / tarantool.SDK / "python"
    for directory in (sdk, sdk / "twr_python_sdk/_guest"):
        (directory / "pathlib.py").write_text(
            "raise RuntimeError('unlisted SDK module executed')"
        )
    command = tarantool.postprocess_commands(conf, tmp_path / "staged.wasm")[-1]
    subprocess.run(command.argv, cwd=conf.project_root, check=True)
    assert not list(sdk.rglob("__pycache__"))
    lock_path = conf.project_root / tarantool.LOCK
    data = json.loads(lock_path.read_text())
    del data["files"][str(Path(command.argv[-2]).relative_to(conf.project_root))]
    lock_path.write_text(json.dumps(data))
    with pytest.raises(BackendError, match="not pinned"):
        tarantool.postprocess_commands(conf, tmp_path / "staged.wasm")

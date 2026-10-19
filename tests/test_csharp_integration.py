import json
import platform
import shutil
import subprocess
from pathlib import Path

import pytest
from utils import CLI_MODES, cli_mode_available, run_cli, run_tool

from tarawasm.backends import get_backend

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/csharp"


def available(mode):
    if not cli_mode_available(mode):
        pytest.skip(f"CLI mode {mode} unavailable")
    if mode == "python" and (
        platform.system() != "Linux" or get_backend("csharp").doctor()
    ):
        pytest.skip("C# requires the pinned Linux amd64 NativeAOT-LLVM toolchain")


@pytest.mark.parametrize("mode", CLI_MODES, ids=lambda value: f"cli:{value}")
def test_csharp_real_imports_exports_resources_and_repeated_builds(tmp_path, mode):
    available(mode)
    project = tmp_path / "project with spaces"
    project.mkdir()
    wit = project / "wit with spaces"
    wit.mkdir()
    shutil.copy(FIXTURE / "world.wit", wit / "world.wit")
    shutil.copytree(FIXTURE / "deps", wit / "deps")
    run_cli(
        project,
        "init",
        "--lang",
        "csharp",
        "--wit",
        "wit with spaces",
        "--world",
        "my-world",
        ".",
        mode=mode,
    )
    # First prove all generated stubs compile, including exported resource types.
    run_cli(project, "bind", mode=mode)
    run_cli(project, "build", mode=mode)
    for path in (project / "src").glob("*.cs"):
        path.unlink()
    shutil.copy(FIXTURE / "Implementation.cs", project / "src/Implementation.cs")
    sources = {path: path.read_bytes() for path in (project / "src").glob("*.cs")}
    lock = (project / "packages.lock.json").read_bytes()
    run_cli(project, "bind", "--tool-help", mode=mode)
    run_cli(project, "build", "--tool-help", mode=mode)
    run_cli(
        project, "toolchain", "use", "csharp", "--mode", "local", "--project", mode=mode
    )
    run_cli(project, "toolchain", "lock", "csharp", mode=mode)
    pinned = json.loads((project / "tarawasm.toolchain.lock.json").read_text())
    assert pinned["languages"]["csharp"]["versions"]["dotnet"] == "10.0.402"
    run_cli(project, "bind", mode=mode)
    run_cli(project, "bind", mode=mode)
    run_cli(project, "build", mode=mode)
    previous = (project / "dist/my-world.wasm").read_bytes()
    assert previous[:8] == b"\0asm\x0d\0\x01\0"
    run_tool(project, "wasm-tools", "validate", "dist/my-world.wasm", mode=mode)
    (project / "package.json").write_text('{"type":"module"}')
    for name in ("host.mjs", "run.mjs"):
        shutil.copy(FIXTURE / name, project / name)
    run_tool(
        project,
        "jco",
        "transpile",
        "dist/my-world.wasm",
        "-o",
        "transpiled",
        "--name",
        "guest",
        "--map",
        "neutral:provider/host-api@0.4.0=../host.mjs",
        mode=mode,
    )
    result = run_tool(
        project, "node", "run.mjs", mode=mode, capture_output=True, text=True
    )
    assert "C# imports/exports/resources: 42" in result.stdout
    (project / "src/broken.cs").write_text("not C# syntax")
    with pytest.raises(subprocess.CalledProcessError):
        run_cli(project, "build", mode=mode)
    assert (project / "dist/my-world.wasm").read_bytes() == previous
    (project / "src/broken.cs").unlink()
    alternate = project / "alternate project"
    alternate.mkdir()
    for name in (
        "Component.csproj",
        "global.json",
        "nuget.config",
        "packages.lock.json",
    ):
        shutil.copy(project / name, alternate / name)
    shutil.copytree(project / "src", alternate / "src")
    run_cli(
        project,
        "build",
        "--src",
        "alternate project/Component.csproj",
        "--out",
        "out path/other.wasm",
        mode=mode,
    )
    assert (project / "out path/other.wasm").read_bytes()[:8] == previous[:8]
    assert all(path.read_bytes() == content for path, content in sources.items())
    assert (project / "packages.lock.json").read_bytes() == lock
    run_cli(project, "clean", mode=mode)
    assert (project / "packages.lock.json").read_bytes() == lock
    assert (project / "tarawasm.toolchain.lock.json").is_file()
    assert (wit / "world.wit").is_file() and (project / "Component.csproj").is_file()
    assert not (project / "dist/my-world.wasm").exists()
    assert (project / "src/Implementation.cs").is_file()
    run_cli(project, "all", mode=mode)
    assert (project / "dist/my-world.wasm").is_file()


@pytest.mark.parametrize("mode", CLI_MODES, ids=lambda value: f"cli:{value}")
def test_csharp_keyword_names_and_world_selection_compile(tmp_path, mode):
    available(mode)
    shutil.copy(FIXTURE / "names.wit", tmp_path / "names.wit")
    run_cli(tmp_path, "init", "--lang", "csharp", "--wit", "names.wit", ".", mode=mode)
    conf = json.loads((tmp_path / "tarawasm.json").read_text())
    assert conf["world"] == "switch-world"
    run_cli(tmp_path, "bind", mode=mode)
    run_cli(tmp_path, "build", mode=mode)
    run_tool(tmp_path, "wasm-tools", "validate", "dist/switch-world.wasm", mode=mode)

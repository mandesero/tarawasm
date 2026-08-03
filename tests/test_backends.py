from pathlib import Path

import pytest

from tarawasm.backends import BackendError, backend_names, get_backend
from tarawasm.config import Config
from tarawasm.wit import WitInterface, WitItem, WitParser, WitWorld

MODEL_WIT = """package test:model@0.1.0;
interface api {
    record point { x: s32, y: s32 }
    variant value { number(s32), text(string), none }
    resource counter {
        constructor(initial: u32);
        get: func() -> u32;
        sum: static func(first: borrow<counter>, second: borrow<counter>) -> u32;
    }
    transform: func(point: point, values: list<option<s32>>) -> result<value, string>;
}
world service {
    export ping: func(value: string) -> string;
    export api;
}
"""


@pytest.fixture
def model(tmp_path):
    path = tmp_path / "model.wit"
    path.write_text(MODEL_WIT)
    document = WitParser().parse(path)
    return path, document.select_world("service")


@pytest.mark.parametrize("language", backend_names())
def test_each_backend_generates_from_actual_world_exports(language, model, tmp_path):
    wit, world = model
    backend = get_backend(language)
    files = backend.initialize_files(world, wit, tmp_path)
    sources = "\n".join(
        content for content in files.values() if isinstance(content, str)
    )
    assert "ping" in sources
    assert "transform" in sources
    assert "counter" in sources.lower()
    assert "wasi:cli/run" not in sources


def test_generated_python_sources_are_syntactically_valid(model, tmp_path):
    wit, world = model
    files = get_backend("python").initialize_files(world, wit, tmp_path)
    for path, content in files.items():
        if path.suffix == ".py":
            compile(content, str(path), "exec")


@pytest.mark.parametrize("language", backend_names())
def test_backend_commands_are_argv_sequences(language, model, tmp_path):
    wit, world = model
    conf = Config(
        language=language,
        world=world.name,
        wit_path=wit,
        wit_package=world.package,
        source=get_backend(language).default_source,
        output=Path("dist/service.wasm"),
        config_path=tmp_path / "tarawasm.json",
    )
    backend = get_backend(language)
    bind = backend.bind_commands(
        conf, world=world.name, wit=wit, tool_args=["--example"]
    )
    build = backend.build_command(
        conf,
        world=world.name,
        wit=wit,
        source=conf.resolve_path(conf.source),
        output=conf.resolve_path(conf.output),
        tool_args=["--example"],
    )
    assert bind and all(isinstance(command.argv, tuple) for command in bind)
    assert isinstance(build.argv, tuple)
    assert "--example" in bind[-1].argv
    assert "--example" in build.argv


def test_go_reports_all_missing_wasip2_interfaces(model):
    _, world = model
    with pytest.raises(
        BackendError,
        match=r"complete versioned wasi:cli/imports@0\.2\.x interface set.*wasi:cli@0\.2\.x/environment",
    ):
        get_backend("go").validate_world(world)


def test_go_does_not_accept_a_partial_wasi_world(model):
    _, world = model
    partial = WitWorld(
        name=world.name,
        package=world.package,
        imports=(
            WitItem(
                name="environment",
                kind="interface",
                interface=WitInterface(
                    name="environment",
                    functions=(),
                    types=(),
                    package="wasi:cli@0.2.0",
                ),
            ),
        ),
        exports=world.exports,
    )
    with pytest.raises(BackendError, match=r"wasi:io@0\.2\.x/streams"):
        get_backend("go").validate_world(partial)

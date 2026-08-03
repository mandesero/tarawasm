import pytest

from tarawasm.wit import WitError, WitParser

MODEL_WIT = """package test:model@0.1.0;

interface api {
    record point { x: s32, y: s32 }
    enum color { red, green }
    flags permissions { read, write }
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

world other { export pong: func() -> string; }
"""


def test_parser_models_functions_interfaces_resources_and_types(tmp_path):
    wit_path = tmp_path / "model.wit"
    wit_path.write_text(MODEL_WIT)
    document = WitParser().parse(wit_path)
    assert document.packages == ("test:model@0.1.0",)
    assert [world.name for world in document.worlds] == ["service", "other"]
    service = document.select_world("service")
    assert service.package == "test:model@0.1.0"
    assert [(item.name, item.kind) for item in service.exports] == [
        ("ping", "function"),
        ("interface-0", "interface"),
    ]
    api = service.exports[1].interface
    assert api is not None
    assert api.name == "api"
    assert {item.kind for item in api.types} >= {
        "record",
        "enum",
        "flags",
        "variant",
        "resource",
    }
    functions = {function.kind: function for function in api.functions}
    assert set(functions) >= {"constructor", "method", "static", "freestanding"}
    assert functions["constructor"].resource == "counter"
    transform = functions["freestanding"]
    assert transform.params[1].type.kind == "list"
    assert transform.result is not None and transform.result.kind == "result"


def test_parser_models_world_defined_types(tmp_path):
    wit_path = tmp_path / "world-types.wit"
    wit_path.write_text(
        """package test:world-types@0.1.0;
world typed {
    variant payload { bytes(list<u8>), number(s32) }
    import receive: func(value: payload);
    export send: func(value: payload);
}
"""
    )

    world = WitParser().parse(wit_path).select_world("typed")

    assert [(item.name, item.kind) for item in world.imports] == [
        ("payload", "type"),
        ("receive", "function"),
    ]
    assert world.imports[0].type is not None
    assert world.imports[0].type.kind == "variant"


def test_world_selection_auto_selects_only_world(tmp_path):
    wit_path = tmp_path / "one.wit"
    wit_path.write_text("package test:one@0.1.0; world only { export ping: func(); }")
    assert WitParser().parse(wit_path).select_world(None).name == "only"


def test_world_selection_requires_explicit_world_when_ambiguous(tmp_path):
    wit_path = tmp_path / "model.wit"
    wit_path.write_text(MODEL_WIT)
    with pytest.raises(WitError, match="multiple worlds: service, other"):
        WitParser().parse(wit_path).select_world(None)


def test_world_selection_lists_worlds_for_unknown_name(tmp_path):
    wit_path = tmp_path / "model.wit"
    wit_path.write_text(MODEL_WIT)
    with pytest.raises(WitError, match="Available worlds: service, other"):
        WitParser().parse(wit_path).select_world("missing")


def test_invalid_wit_reports_path_and_reason(tmp_path):
    wit_path = tmp_path / "invalid.wit"
    wit_path.write_text("this is not wit")
    with pytest.raises(WitError, match=str(wit_path)):
        WitParser().parse(wit_path)

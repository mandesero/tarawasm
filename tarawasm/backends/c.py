from __future__ import annotations

from importlib.resources import as_file, files
from pathlib import Path

from tarawasm.wit import WitFunction, WitType

from .base import Command, LanguageBackend, snake

_PRIMITIVES = {
    "bool": "bool",
    "u8": "uint8_t",
    "u16": "uint16_t",
    "u32": "uint32_t",
    "u64": "uint64_t",
    "s8": "int8_t",
    "s16": "int16_t",
    "s32": "int32_t",
    "s64": "int64_t",
    "f32": "float",
    "f64": "double",
    "char": "uint32_t",
}


def _type_token(value: WitType) -> str:
    if value.kind == "primitive":
        return snake(value.name or "value")
    if value.name:
        return snake(value.name)
    if value.kind == "tuple":
        return f"tuple{len(value.value)}_" + "_".join(
            _type_token(item) for item in value.value
        )
    if value.kind in {"list", "option"}:
        return f"{value.kind}_{_type_token(value.value)}"
    return snake(value.kind)


def _c_type(
    value: WitType, world_prefix: str, interface_prefix: str
) -> tuple[str, bool]:
    if value.kind == "primitive":
        if value.name == "string":
            return f"{world_prefix}_string_t", True
        return _PRIMITIVES[value.name or ""], False
    if value.kind == "handle":
        handle_kind, resource = value.value
        return (
            f"{interface_prefix}_{handle_kind}_{snake(resource.name or 'resource')}_t",
            False,
        )
    if value.name:
        return f"{interface_prefix}_{snake(value.name)}_t", value.kind in {
            "record",
            "variant",
        }
    return f"{world_prefix}_{_type_token(value)}_t", True


def _declaration(
    prefix: str,
    function: WitFunction,
    world_prefix: str,
    interface_prefix: str,
) -> str:
    params: list[str] = []
    for param in function.params:
        c_type, pointer = _c_type(param.type, world_prefix, interface_prefix)
        params.append(f"{c_type}{' *' if pointer else ' '}{snake(param.name)}")
    if function.result is None:
        result = "void"
    elif function.result.kind == "result":
        result = "bool"
        ok, err = function.result.value
        if ok is not None:
            c_type, _ = _c_type(ok, world_prefix, interface_prefix)
            params.append(f"{c_type} *ret")
        if err is not None:
            c_type, _ = _c_type(err, world_prefix, interface_prefix)
            params.append(f"{c_type} *err")
    else:
        c_type, pointer = _c_type(function.result, world_prefix, interface_prefix)
        if pointer:
            result = "void"
            params.append(f"{c_type} *ret")
        else:
            result = c_type
    return f"{result} {prefix}_{snake(function.name)}({', '.join(params) or 'void'})"


class CBackend(LanguageBackend):
    name = "c"
    default_source = Path("component.c")
    required_tools = ("wit-bindgen", "clang", "wasm-tools")

    def initialize_files(self, world, wit_path, project_root):
        result = super().initialize_files(world, wit_path, project_root)
        resource = files("tarawasm.lang_deps") / "wasi_snapshot_preview1.wasm"
        with as_file(resource) as source:
            result[Path(".tarawasm/build/c/wasi_snapshot_preview1.wasm")] = (
                source.read_bytes()
            )
        return result

    def generate_source(self, world):
        lines = [f'#include "bindings/{snake(world.name)}.h"', ""]
        world_prefix = snake(world.name)
        for item in world.exports:
            if item.function is not None:
                declaration = _declaration(
                    f"exports_{world_prefix}",
                    item.function,
                    world_prefix,
                    f"exports_{world_prefix}",
                )
                lines.extend(
                    [
                        f"/* TODO: implement WIT item {item.function.name}. */",
                        f"{declaration} {{",
                        "    __builtin_trap();",
                        "}",
                        "",
                    ]
                )
            elif item.interface is not None:
                package = item.interface.package.split("@", 1)[0].replace(":", "_")
                prefix = f"exports_{snake(package)}_{snake(item.interface.name)}"
                resources = sorted(
                    {
                        function.resource
                        for function in item.interface.functions
                        if function.resource is not None
                    }
                )
                for resource in resources:
                    lines.extend(
                        [
                            f"void {prefix}_{snake(resource)}_destructor(",
                            f"    {prefix}_{snake(resource)}_t *rep) {{",
                            "    (void)rep;",
                            "}",
                            "",
                        ]
                    )
                for function in item.interface.functions:
                    operation = snake(function.name)
                    if function.kind == "constructor":
                        operation = f"constructor_{snake(function.resource or '')}"
                    elif function.kind in {"method", "static"}:
                        operation = (
                            f"{function.kind}_{snake(function.resource or '')}_"
                            f"{snake(function.name.split('.')[-1])}"
                        )
                    normalized = WitFunction(
                        operation,
                        function.kind,
                        function.params,
                        function.result,
                        function.resource,
                    )
                    declaration = _declaration(prefix, normalized, world_prefix, prefix)
                    lines.extend(
                        [
                            f"/* TODO: implement WIT item {function.name}. */",
                            f"{declaration} {{",
                            "    __builtin_trap();",
                            "}",
                            "",
                        ]
                    )
        if len(lines) == 2:
            lines.extend(
                ["/* Implement the exports declared by the generated header. */", ""]
            )
        return "\n".join(lines)

    def bind_command(self, conf, *, world, wit, tool_args):
        return Command(
            (
                "wit-bindgen",
                "c",
                "--world",
                world,
                "--out-dir",
                "bindings",
                *tool_args,
                str(wit),
            )
        )

    def build_command(self, conf, *, world, wit, source, output, tool_args):
        intermediate = conf.build_dir / "c" / f"{world}.wasm"
        return Command(
            (
                "clang",
                *tool_args,
                str(source),
                f"bindings/{world}.c",
                f"bindings/{world}_component_type.o",
                "-o",
                str(intermediate),
                "-mexec-model=reactor",
            )
        )

    def locate_artifact(self, conf, requested):
        return requested

    def finish_build_command(self, conf, *, world, output):
        return Command(
            (
                "wasm-tools",
                "component",
                "new",
                str(conf.build_dir / "c" / f"{world}.wasm"),
                "--adapt",
                str(conf.build_dir / "c/wasi_snapshot_preview1.wasm"),
                "-o",
                str(output),
            )
        )

    def generated_artifacts(self, conf):
        return (conf.project_root / "bindings",)

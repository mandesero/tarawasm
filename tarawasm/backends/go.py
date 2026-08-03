from __future__ import annotations

from pathlib import Path

from tarawasm.wit import WitFunction, WitType

from .base import BackendError, Command, LanguageBackend, pascal, snake

_PRIMITIVES = {
    "bool": "bool",
    "u8": "uint8",
    "u16": "uint16",
    "u32": "uint32",
    "u64": "uint64",
    "s8": "int8",
    "s16": "int16",
    "s32": "int32",
    "s64": "int64",
    "f32": "float32",
    "f64": "float64",
    "char": "rune",
    "string": "string",
}

# TinyGo's built-in wasip2 target is linked against the imports of
# wasi:cli/imports@0.2.0. Keep this explicit so an incompatible world fails
# before TinyGo reaches component linking with a sequence of missing imports.
_WASIP2_IMPORTS = {
    ("wasi:io", "error"),
    ("wasi:io", "poll"),
    ("wasi:io", "streams"),
    ("wasi:clocks", "monotonic-clock"),
    ("wasi:clocks", "wall-clock"),
    ("wasi:filesystem", "types"),
    ("wasi:filesystem", "preopens"),
    ("wasi:sockets", "network"),
    ("wasi:sockets", "instance-network"),
    ("wasi:sockets", "ip-name-lookup"),
    ("wasi:sockets", "tcp"),
    ("wasi:sockets", "tcp-create-socket"),
    ("wasi:sockets", "udp"),
    ("wasi:sockets", "udp-create-socket"),
    ("wasi:random", "insecure-seed"),
    ("wasi:random", "insecure"),
    ("wasi:random", "random"),
    ("wasi:cli", "environment"),
    ("wasi:cli", "exit"),
    ("wasi:cli", "stdin"),
    ("wasi:cli", "stdout"),
    ("wasi:cli", "stderr"),
    ("wasi:cli", "terminal-input"),
    ("wasi:cli", "terminal-output"),
    ("wasi:cli", "terminal-stdin"),
    ("wasi:cli", "terminal-stdout"),
    ("wasi:cli", "terminal-stderr"),
}


def _go_type(value: WitType, package: str = "") -> str:
    if value.kind == "primitive":
        return _PRIMITIVES[value.name or ""]
    if (
        value.kind in {"alias", "record", "variant", "enum", "flags", "resource"}
        and value.name
    ):
        return f"{package}.{pascal(value.name)}" if package else pascal(value.name)
    if value.kind == "list":
        return f"cm.List[{_go_type(value.value, package)}]"
    if value.kind == "option":
        return f"cm.Option[{_go_type(value.value, package)}]"
    if value.kind == "tuple":
        return f"cm.Tuple[{', '.join(_go_type(item, package) for item in value.value)}]"
    if value.kind == "handle":
        handle_kind, resource = value.value
        if handle_kind == "own" and resource.name:
            return (
                f"{package}.{pascal(resource.name)}"
                if package
                else pascal(resource.name)
            )
        return "cm.Rep"
    if value.kind == "result":
        ok, err = value.value
        if ok is None and err is None:
            return "cm.BoolResult"
        ok_type = "struct{}" if ok is None else _go_type(ok, package)
        err_type = "struct{}" if err is None else _go_type(err, package)
        if ok is not None and ok.name:
            shape = (
                f"{package}.{pascal(ok.name)}Shape"
                if package
                else f"{pascal(ok.name)}Shape"
            )
        else:
            shape = f"cm.ResultShape[{ok_type}, {err_type}]"
        return f"cm.Result[{shape}, {ok_type}, {err_type}]"
    return "any"


def _go_function(function: WitFunction, package: str = "") -> str:
    args = []
    for param in function.params:
        if function.kind == "method" and param.name == "self":
            args.append("self cm.Rep")
        else:
            args.append(f"{snake(param.name)} {_go_type(param.type, package)}")
    result = (
        ""
        if function.result is None
        else f" (result {_go_type(function.result, package)})"
    )
    return f"func({', '.join(args)}){result}"


def _package_parts(package: str) -> tuple[str, str]:
    base = package.split("@", 1)[0]
    namespace, name = base.split(":", 1)
    return snake(namespace), snake(name)


class GoBackend(LanguageBackend):
    name = "go"
    default_source = Path("main.go")
    required_tools = ("go", "tinygo")

    def validate_world(self, world):
        imports = {
            (item.interface.package.partition("@")[0], item.interface.name)
            for item in world.imports
            if item.interface is not None
            and item.interface.package.partition("@")[2].startswith("0.2.")
        }
        missing = sorted(_WASIP2_IMPORTS - imports)
        if missing:
            rendered = ", ".join(f"{package}@0.2.x/{name}" for package, name in missing)
            raise BackendError(
                f"Go backend cannot build world '{world.name}': TinyGo's wasip2 "
                "target requires the complete versioned wasi:cli/imports@0.2.x "
                "interface "
                f"set. Missing imports: {rendered}. Include the versioned "
                "wasi:cli/imports world in this world before building."
            )

    def initialize_files(self, world, wit_path, project_root):
        files = super().initialize_files(world, wit_path, project_root)
        module = f"tarawasm/{snake(world.name)}"
        files[Path("go.mod")] = f"module {module}\n\ngo 1.25.0\n"
        return files

    def generate_source(self, world):
        module = f"tarawasm/{snake(world.name)}"
        namespace, package_name = _package_parts(world.package)
        imports: list[tuple[str, str]] = []
        direct = [item.function for item in world.exports if item.function]
        if direct:
            imports.append(
                (
                    "world",
                    f"{module}/internal/{namespace}/{package_name}/{snake(world.name)}",
                )
            )
        for item in world.exports:
            if item.interface is not None:
                interface_namespace, interface_package = _package_parts(
                    item.interface.package
                )
                imports.append(
                    (
                        snake(item.interface.name),
                        (
                            f"{module}/internal/{interface_namespace}/"
                            f"{interface_package}/{snake(item.interface.name)}"
                        ),
                    )
                )
        needs_cm = any(
            token in repr(world)
            for token in ("list", "option", "tuple", "result", "handle")
        )
        lines = ["package main", "", "import ("]
        if needs_cm:
            lines.append('    "go.bytecodealliance.org/cm"')
        for alias, path in imports:
            lines.append(f'    {alias} "{path}"')
        lines.extend([")", "", "func init() {"])
        for function in direct:
            name = pascal(function.name)
            lines.append(f"    world.Exports.{name} = {_go_function(function)} {{")
            lines.append(f'        panic("TODO: implement WIT item {function.name}")')
            lines.append("    }")
        for item in world.exports:
            interface = item.interface
            if interface is None:
                continue
            alias = snake(interface.name)
            for function in interface.functions:
                operation = pascal(function.name.split(".")[-1])
                if function.resource:
                    if function.kind == "constructor":
                        operation = "Constructor"
                    target = f"{alias}.Exports.{pascal(function.resource)}.{operation}"
                else:
                    target = f"{alias}.Exports.{operation}"
                lines.append(f"    {target} = {_go_function(function, alias)} {{")
                lines.append(
                    f'        panic("TODO: implement WIT item {function.name}")'
                )
                lines.append("    }")
        lines.extend(["}", "", "func main() {}", ""])
        return "\n".join(lines)

    def bind_command(self, conf, *, world, wit, tool_args):
        return Command(
            (
                "go",
                "tool",
                "wit-bindgen-go",
                "generate",
                *tool_args,
                "--world",
                world,
                "-o",
                "internal",
                str(wit),
            )
        )

    def bind_commands(self, conf, *, world, wit, tool_args):
        return (
            Command(
                (
                    "go",
                    "get",
                    "-tool",
                    "go.bytecodealliance.org/cmd/wit-bindgen-go@v0.7.0",
                )
            ),
            Command(("go", "get", "go.bytecodealliance.org@v0.7.0")),
            self.bind_command(conf, world=world, wit=wit, tool_args=tool_args),
        )

    def build_command(self, conf, *, world, wit, source, output, tool_args):
        return Command(
            (
                "tinygo",
                "build",
                "-target=wasip2",
                "-o",
                str(output),
                "--wit-package",
                str(wit),
                "--wit-world",
                world,
                *tool_args,
                str(source),
            ),
            {"GOTOOLCHAIN": "go1.25.6+auto"},
        )

    def generated_artifacts(self, conf):
        return (conf.project_root / "internal",)

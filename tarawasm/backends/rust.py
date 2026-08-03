from __future__ import annotations

from pathlib import Path

from tarawasm.wit import WitType

from .base import Command, LanguageBackend, pascal, snake

_PRIMITIVES = {
    "bool": "bool",
    "u8": "u8",
    "u16": "u16",
    "u32": "u32",
    "u64": "u64",
    "s8": "i8",
    "s16": "i16",
    "s32": "i32",
    "s64": "i64",
    "f32": "f32",
    "f64": "f64",
    "char": "char",
    "string": "String",
}


def _rust_type(value: WitType, module: str = "bindings") -> str:
    if value.kind == "primitive":
        return _PRIMITIVES[value.name or ""]
    if value.name:
        return f"{module}::{pascal(value.name)}"
    if value.kind == "list":
        return f"Vec<{_rust_type(value.value, module)}>"
    if value.kind == "option":
        return f"Option<{_rust_type(value.value, module)}>"
    if value.kind == "tuple":
        return f"({', '.join(_rust_type(item, module) for item in value.value)})"
    if value.kind == "result":
        ok, err = value.value
        ok_type = "()" if ok is None else _rust_type(ok, module)
        err_type = "()" if err is None else _rust_type(err, module)
        return f"Result<{ok_type}, {err_type}>"
    return "()"


class RustBackend(LanguageBackend):
    name = "rust"
    default_source = Path("src/lib.rs")
    required_tools = ("cargo", "cargo-component")

    def initialize_files(self, world, wit_path, project_root):
        files = super().initialize_files(world, wit_path, project_root)
        try:
            target_path = (
                wit_path.resolve().relative_to(project_root.resolve()).as_posix()
            )
        except ValueError:
            target_path = str(wit_path.resolve())
        crate_name = snake(world.name).replace("_", "-") or "component"
        dependency_lines = ""
        if wit_path.name == "imported-wit":
            packages = sorted(
                {
                    item.interface.package.split("@", 1)[0]
                    for item in (*world.imports, *world.exports)
                    if item.interface is not None
                    and item.interface.package.split("@", 1)[0]
                    != world.package.split("@", 1)[0]
                }
            )
            dependency_lines = "".join(
                f'"{package}" = {{ path = "{target_path}/deps/'
                f'{package.split(":", 1)[1]}" }}\n'
                for package in packages
            )
        files[Path("Cargo.toml")] = f"""[package]
name = "{crate_name}"
version = "0.1.0"
edition = "2021"

[dependencies]
wit-bindgen-rt = {{ version = "0.44.0", features = ["bitflags"] }}

[lib]
crate-type = ["cdylib"]

[package.metadata.component]
package = "{world.package.split("@", 1)[0]}"

[package.metadata.component.target]
path = "{target_path}"
world = "{world.name}"

[package.metadata.component.target.dependencies]
{dependency_lines}
"""
        return files

    def generate_source(self, world):
        lines = ["#[allow(warnings)]", "mod bindings;", "", "struct Component;", ""]
        direct = [item.function for item in world.exports if item.function]
        if direct:
            lines.extend(["impl bindings::Guest for Component {"])
            for function in direct:
                args = ", ".join(
                    f"_{snake(p.name)}: {_rust_type(p.type)}" for p in function.params
                )
                result = (
                    ""
                    if function.result is None
                    else f" -> {_rust_type(function.result)}"
                )
                lines.extend(
                    [
                        f"    fn {snake(function.name)}({args}){result} {{",
                        f'        todo!("implement WIT item {function.name}")',
                        "    }",
                    ]
                )
            lines.extend(["}", ""])
        for item in world.exports:
            interface = item.interface
            if interface is None:
                continue
            package = interface.package.split("@", 1)[0]
            namespace, package_name = package.split(":", 1)
            module = (
                f"bindings::exports::{snake(namespace)}::{snake(package_name)}::"
                f"{snake(interface.name)}"
            )
            functions = [f for f in interface.functions if f.kind == "freestanding"]
            resources = sorted(
                {f.resource for f in interface.functions if f.resource is not None}
            )
            if functions or resources:
                lines.append(f"impl {module}::Guest for Component {{")
                for resource in resources:
                    lines.append(f"    type {pascal(resource)} = {pascal(resource)};")
                for function in functions:
                    args = ", ".join(
                        f"_{snake(p.name)}: {_rust_type(p.type, module)}"
                        for p in function.params
                    )
                    result = (
                        ""
                        if function.result is None
                        else f" -> {_rust_type(function.result, module)}"
                    )
                    lines.extend(
                        [
                            f"    fn {snake(function.name)}({args}){result} {{",
                            f'        todo!("implement WIT item {function.name}")',
                            "    }",
                        ]
                    )
                lines.extend(["}", ""])
            for resource in resources:
                resource_type = pascal(resource)
                lines.extend(
                    [
                        f"struct {resource_type};",
                        "",
                        f"impl {module}::Guest{resource_type} for {resource_type} {{",
                    ]
                )
                for function in [
                    f for f in interface.functions if f.resource == resource
                ]:
                    arguments: list[str] = []
                    for param in function.params:
                        if function.kind == "method" and param.name == "self":
                            arguments.append("&self")
                            continue
                        if param.type.kind == "handle":
                            handle_kind, handle_resource = param.type.value
                            if handle_kind == "borrow" and handle_resource.name:
                                rust_type = f"{module}::{pascal(handle_resource.name)}Borrow<'_>"
                            else:
                                rust_type = _rust_type(param.type, module)
                        else:
                            rust_type = _rust_type(param.type, module)
                        arguments.append(f"_{snake(param.name)}: {rust_type}")
                    name = (
                        "new"
                        if function.kind == "constructor"
                        else snake(function.name.split(".")[-1])
                    )
                    if function.kind == "constructor":
                        result = " -> Self"
                    else:
                        result = (
                            ""
                            if function.result is None
                            else f" -> {_rust_type(function.result, module)}"
                        )
                    lines.extend(
                        [
                            f"    fn {name}({', '.join(arguments)}){result} {{",
                            f'        todo!("implement WIT item {function.name}")',
                            "    }",
                        ]
                    )
                lines.extend(["}", ""])
        lines.extend(["bindings::export!(Component with_types_in bindings);", ""])
        return "\n".join(lines)

    def bind_command(self, conf, *, world, wit, tool_args):
        return Command(("cargo", "component", "bindings", *tool_args))

    def build_command(self, conf, *, world, wit, source, output, tool_args):
        return Command(
            ("cargo", "component", "build", "--release", *tool_args),
            {"CARGO_TARGET_DIR": str(conf.build_dir / "rust")},
        )

    def locate_artifact(self, conf, requested):
        crate = snake(conf.world)
        return conf.build_dir / "rust/wasm32-wasip1/release" / f"{crate}.wasm"

    def generated_artifacts(self, conf):
        return (conf.project_root / "src/bindings.rs", conf.project_root / "Cargo.lock")

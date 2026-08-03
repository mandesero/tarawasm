from __future__ import annotations

import os
from pathlib import Path

from tarawasm.wit import WitFunction, WitWorld

from .base import Command, LanguageBackend, pascal, snake


def _method(function: WitFunction, indent: str = "    ") -> list[str]:
    args = [snake(param.name) for param in function.params if param.name != "self"]
    if function.kind in {"method", "constructor"}:
        signature = ["self", *args]
    elif function.kind == "static":
        signature = ["cls", *args]
    else:
        signature = ["self", *args]
    name = (
        "__init__"
        if function.kind == "constructor"
        else snake(function.name.split(".")[-1])
    )
    lines: list[str] = []
    if function.kind == "static":
        lines.extend(
            [f"{indent}@classmethod", f"{indent}def {name}({', '.join(signature)}):"]
        )
    else:
        lines.append(f"{indent}def {name}({', '.join(signature)}):")
    lines.append(
        f'{indent}    raise NotImplementedError("TODO: implement WIT item {function.name}")'
    )
    return lines


class PythonBackend(LanguageBackend):
    name = "python"
    default_source = Path("main.py")
    required_tools = ("componentize-py",)

    def initialize_files(self, world, wit_path, project_root):
        files = {self.default_source: self.generate_source(world)}
        for item in world.exports:
            interface = item.interface
            if interface is None or not any(
                function.resource is not None for function in interface.functions
            ):
                continue
            lines = [f"from wit_world.exports import {snake(interface.name)}", ""]
            for resource in sorted(
                {f.resource for f in interface.functions if f.resource is not None}
            ):
                lines.append(
                    f"class {pascal(resource)}({snake(interface.name)}.{pascal(resource)}):"
                )
                for function in [
                    f for f in interface.functions if f.resource == resource
                ]:
                    lines.extend(_method(function))
                lines.append("")
            files[Path(f"{snake(interface.name)}.py")] = (
                "\n".join(lines).rstrip() + "\n"
            )
        return files

    def generate_source(self, world: WitWorld) -> str:
        lines = ["import wit_world", "from wit_world import exports", ""]
        direct = [item.function for item in world.exports if item.function]
        if direct:
            lines.append("class WitWorld(wit_world.WitWorld):")
            for function in direct:
                lines.extend(_method(function))
            lines.append("")
        for item in world.exports:
            interface = item.interface
            if interface is None:
                continue
            if any(function.resource is not None for function in interface.functions):
                lines.insert(0, f"import {snake(interface.name)}")
            lines.append(
                f"class {pascal(interface.name)}(exports.{pascal(interface.name)}):"
            )
            functions = [f for f in interface.functions if f.kind == "freestanding"]
            if functions:
                for function in functions:
                    lines.extend(_method(function))
            else:
                lines.append("    pass")
            lines.append("")
        if len(lines) == 2:
            lines.extend(["# The selected world has no exports.", ""])
        return "\n".join(lines).rstrip() + "\n"

    def bind_command(self, conf, *, world, wit, tool_args):
        return Command(
            (
                "componentize-py",
                f"--wit-path={wit}",
                f"--world={world}",
                *tool_args,
                "bindings",
                ".",
            )
        )

    def build_command(self, conf, *, world, wit, source, output, tool_args):
        python_paths: list[str] = []
        persistent = os.environ.get("TARAWASM_PY_SITE_PACKAGES")
        if persistent:
            python_paths.extend(("--python-path", ".", "--python-path", persistent))
        return Command(
            (
                "componentize-py",
                f"--wit-path={wit}",
                f"--world={world}",
                "componentize",
                *python_paths,
                *tool_args,
                source.stem,
                "-o",
                str(output),
            )
        )

    def generated_artifacts(self, conf):
        return (conf.project_root / "wit_world",)

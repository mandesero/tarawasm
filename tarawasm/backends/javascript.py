from __future__ import annotations

from pathlib import Path

from .base import Command, LanguageBackend, pascal, snake


class JavaScriptBackend(LanguageBackend):
    name = "js"
    default_source = Path("main.js")
    required_tools = ("jco",)

    def generate_source(self, world):
        lines: list[str] = []
        direct = [item.function for item in world.exports if item.function]
        for function in direct:
            args = ", ".join(snake(param.name) for param in function.params)
            lines.extend(
                [
                    f"export function {snake(function.name)}({args}) {{",
                    f'    throw new Error("TODO: implement WIT item {function.name}");',
                    "}",
                    "",
                ]
            )
        for item in world.exports:
            interface = item.interface
            if interface is None:
                continue
            resources = sorted(
                {f.resource for f in interface.functions if f.resource is not None}
            )
            for resource in resources:
                lines.append(f"class {pascal(resource)} {{")
                for function in [
                    f for f in interface.functions if f.resource == resource
                ]:
                    args = [snake(p.name) for p in function.params if p.name != "self"]
                    if function.kind == "constructor":
                        declaration = f"    constructor({', '.join(args)}) {{"
                    elif function.kind == "static":
                        declaration = f"    static {snake(function.name.split('.')[-1])}({', '.join(args)}) {{"
                    else:
                        declaration = f"    {snake(function.name.split('.')[-1])}({', '.join(args)}) {{"
                    lines.extend(
                        [
                            declaration,
                            f'        throw new Error("TODO: implement WIT item {function.name}");',
                            "    }",
                        ]
                    )
                lines.extend(["}", ""])
            lines.append(f"export const {snake(interface.name)} = {{")
            for function in interface.functions:
                if function.kind != "freestanding":
                    continue
                args = ", ".join(snake(param.name) for param in function.params)
                method = snake(function.name)
                lines.extend(
                    [
                        f"    {method}: ({args}) => {{",
                        f'        throw new Error("TODO: implement WIT item {function.name}");',
                        "    },",
                    ]
                )
            for resource in resources:
                lines.append(f"    {pascal(resource)},")
            lines.extend(["};", ""])
        return "\n".join(lines).rstrip() + "\n"

    def bind_command(self, conf, *, world, wit, tool_args):
        return Command(
            (
                "jco",
                "guest-types",
                *tool_args,
                "--world-name",
                world,
                "-o",
                "internal",
                str(wit),
            )
        )

    def build_command(self, conf, *, world, wit, source, output, tool_args):
        return Command(
            (
                "jco",
                "componentize",
                *tool_args,
                str(source),
                "--wit",
                str(wit),
                "--world-name",
                world,
                "--out",
                str(output),
                "--disable",
                "all",
                "--enable",
                "stdio",
            )
        )

    def generated_artifacts(self, conf):
        return (conf.project_root / "internal",)

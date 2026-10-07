from __future__ import annotations

from pathlib import Path

from .base import BackendError, Command, LanguageBackend, pascal, snake

FEATURES = ("clocks", "http", "random", "stdio", "fetch-event")


def camel(name: str) -> str:
    first, *rest = snake(name).split("_")
    return first + "".join(part.capitalize() for part in rest)


def feature_args(tool_args: list[str]) -> tuple[list[str], list[str]]:
    """Apply user selectors in order to the stdio-only default."""
    enabled = {"stdio"}
    remaining = []
    index = 0
    while index < len(tool_args):
        token = tool_args[index]
        option, separator, value = token.partition("=")
        if token.startswith("-d") and not token.startswith("--") and len(token) > 2:
            option, separator, value = "-d", "=", token[2:].removeprefix("=")
        if option not in {"--enable", "--disable", "-d"}:
            remaining.append(token)
            index += 1
            continue
        values = [value] if separator else []
        index += 1
        while index < len(tool_args) and not tool_args[index].startswith("-"):
            values.append(tool_args[index])
            index += 1
        if not values or any(v not in (*FEATURES, "all") for v in values):
            raise BackendError(
                f"{option} requires JS feature names: {', '.join(FEATURES)}, all."
            )
        selected = set(FEATURES) if "all" in values else set(values)
        if option == "--enable":
            enabled.update(selected)
        else:
            enabled.difference_update(selected)
    disabled = [feature for feature in FEATURES if feature not in enabled]
    # Emit one selector per direction; Jco never sees conflicting defaults.
    return remaining, [
        *(["--disable", *disabled] if disabled else []),
        *(["--enable", *[f for f in FEATURES if f in enabled]] if enabled else []),
    ]


class JavaScriptBackend(LanguageBackend):
    name = "js"
    default_source = Path("main.js")
    required_tools = ("jco",)

    def generate_source(self, world):
        lines: list[str] = []
        direct = [item.function for item in world.exports if item.function]
        for function in direct:
            args = ", ".join(camel(param.name) for param in function.params)
            lines.extend(
                [
                    f"export function {camel(function.name)}({args}) {{",
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
                    args = [camel(p.name) for p in function.params if p.name != "self"]
                    if function.kind == "constructor":
                        declaration = f"    constructor({', '.join(args)}) {{"
                    elif function.kind == "static":
                        declaration = f"    static {camel(function.name.split('.')[-1])}({', '.join(args)}) {{"
                    else:
                        declaration = f"    {camel(function.name.split('.')[-1])}({', '.join(args)}) {{"
                    lines.extend(
                        [
                            declaration,
                            f'        throw new Error("TODO: implement WIT item {function.name}");',
                            "    }",
                        ]
                    )
                lines.extend(["}", ""])
            lines.append(f"export const {camel(interface.name)} = {{")
            for function in interface.functions:
                if function.kind != "freestanding":
                    continue
                args = ", ".join(camel(param.name) for param in function.params)
                method = camel(function.name)
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
        passthrough, features = feature_args(tool_args)
        return Command(
            (
                "jco",
                "componentize",
                "--bundle",
                *passthrough,
                str(source),
                "--wit",
                str(wit),
                "--world-name",
                world,
                "--out",
                str(output),
                *features,
            )
        )

    def generated_artifacts(self, conf):
        return (conf.project_root / "internal",)

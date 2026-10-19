from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from tarawasm.wit import WitType

from .base import BackendError, Command, LanguageBackend


class CSharpBackend(LanguageBackend):
    name = "csharp"
    default_source = Path("Component.csproj")
    required_tools = ("dotnet", "wasm-tools")

    def doctor(self):
        from tarawasm.csharp import require_platform

        try:
            require_platform()
        except BackendError:
            return ["Linux amd64 NativeAOT-LLVM toolchain"]
        return super().doctor()

    def validate_world(self, world):
        def inspect(value: WitType | None):
            if value is None:
                return
            unsupported = {"future", "stream", "error-context", "fixed-length-list"}
            feature = (
                value.name
                if value.kind == "primitive"
                else (
                    value.value
                    if value.kind == "alias" and isinstance(value.value, str)
                    else value.kind
                )
            )
            if feature in unsupported:
                raise BackendError(
                    f"C# wit-bindgen 0.58.0 does not support WIT {feature}: {value.name or '(anonymous)'}."
                )
            if isinstance(value.value, WitType):
                inspect(value.value)
            elif isinstance(value.value, tuple):
                for child in value.value:
                    if isinstance(child, WitType):
                        inspect(child)
                    elif isinstance(child, tuple):
                        for nested in child:
                            if isinstance(nested, WitType):
                                inspect(nested)

        for item in (*world.imports, *world.exports):
            inspect(item.type)
            functions = (item.function,) if item.function else ()
            if item.interface:
                functions = item.interface.functions
                for value in item.interface.types:
                    inspect(value)
            for function in functions:
                if "async" in function.kind:
                    raise BackendError(
                        f"C# does not support async WIT function '{function.name}'."
                    )
                for param in function.params:
                    inspect(param.type)
                inspect(function.result)

    def validate_bind_world(self, world):
        self.validate_world(world)

    def generate_source(self, world):
        raise BackendError("C# stubs require the original WIT; use initialize_files.")

    def initialize_files(self, world, wit_path, project_root):
        from tarawasm.csharp import implementation_files, project_files

        self.validate_world(world)
        return {**project_files(), **implementation_files(wit_path, world.name)}

    def initialize_from_import(self, world, extracted, final_wit, project_root):
        return self.initialize_files(world, extracted, project_root)

    def _command(self, action, conf, world, wit, source, output, tool_args):
        from tarawasm.toolchains.runtime import executable

        if source.suffix != ".csproj":
            raise BackendError(
                "C# source/--src must name a .csproj, not a .cs file or directory."
            )
        prefix = (
            (sys.executable, "_csharp")
            if "__compiled__" in globals() or getattr(sys, "frozen", False)
            else (sys.executable, "-m", "tarawasm.cli", "_csharp")
        )
        key = hashlib.sha256(str(source).encode()).hexdigest()[:16]
        return Command(
            (
                *prefix,
                action,
                "--dotnet",
                executable("dotnet"),
                "--wasm-tools",
                executable("wasm-tools"),
                "--project",
                str(source),
                "--wit",
                str(wit),
                "--world",
                world,
                "--root",
                str(conf.build_dir / "csharp" / key),
                *(["--output", str(output)] if output else []),
                "--",
                *tool_args,
            )
        )

    def bind_command(self, conf, *, world, wit, tool_args):
        return self._command(
            "bind", conf, world, wit, conf.resolve_path(conf.source), None, tool_args
        )

    def build_command(self, conf, *, world, wit, source, output, tool_args):
        return self._command("build", conf, world, wit, source, output, tool_args)

from __future__ import annotations

import os
from pathlib import Path

from .config import LANG_CFGS, Config


def bind_args(
    lang: str,
    conf: Config,
    *,
    world_override: str | None = None,
    wit_override: Path | None = None,
    tool_args: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    passthrough = list(tool_args or [])
    cfg = LANG_CFGS[lang]
    wit_path = str(wit_override or conf.wit_path)
    world = world_override or conf.world
    wasm_file = conf.wasm_file

    if lang == "python":
        cmd = ["componentize-py"]
        args = [
            f"{cfg['wit-flag']}={wit_path}",
            f"--world={world}",
            *passthrough,
            "bindings",
            ".",
        ]
    elif lang == "go":
        cmd = ["go", "tool", "wit-bindgen-go"]
        args = ["generate", *passthrough, "--world", world, "-o", "internal", wit_path]
    elif lang == "js":
        cmd = ["jco", "guest-types"]
        args = [*passthrough, "-o", "internal", wit_path]
    elif lang == "rust":
        cmd = ["cargo", "component", "bindings"]
        args = [*passthrough]
    elif lang == "c":
        cmd = ["wit-bindgen", "c"]
        args = [*passthrough, wasm_file]
    else:
        raise ValueError(f"Unsupported lang: {lang}")

    return cmd, args


def build_args(
    lang: str,
    conf: Config,
    *,
    world_override: str | None = None,
    wit_override: Path | None = None,
    src_override: str | None = None,
    out_override: str | None = None,
    tool_args: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    passthrough = list(tool_args or [])
    cfg = LANG_CFGS[lang]
    world = world_override or conf.world
    src = src_override or conf.src_file
    wit_path = str(wit_override or conf.wit_path)
    out = out_override or f"{world}.wasm"

    if lang == "python":
        cmd = ["componentize-py"]
        python_paths: list[str] = []
        persistent_site_packages = os.environ.get("TARAWASM_PY_SITE_PACKAGES")
        if persistent_site_packages:
            # `componentize-py` does not inherit regular PYTHONPATH during componentization.
            python_paths.extend(["--python-path", "."])
            python_paths.extend(["--python-path", persistent_site_packages])
        args = [
            f"{cfg['wit-flag']}={wit_path}",
            f"--world={world}",
            "componentize",
            *python_paths,
            *passthrough,
            Path(src).stem,
            "-o",
            out,
        ]
    elif lang == "go":
        cmd = ["tinygo", "build"]
        args = [
            f"-target={cfg['tinygo-target']}",
            "-o",
            out,
            "--wit-package",
            wit_path,
            "--wit-world",
            world,
            *passthrough,
            src,
        ]
    elif lang == "js":
        cmd = ["jco", "componentize"]
        args = [
            *passthrough,
            src,
            cfg["wit-flag"],
            wit_path,
            "--world-name",
            world,
            "--out",
            out,
            "--disable",
            "all",
            "--enable",
            "stdio",
        ]
    elif lang == "rust":
        cmd = ["cargo", "component", "build"]
        args = ["--release", *passthrough]
    elif lang == "c":
        cmd = ["clang"]
        intermediate = (
            conf.resolve_path(conf.state_dir) / "build" / "c" / f"{world}.wasm"
        )
        args = [
            *passthrough,
            src,
            f"{world}.c",
            f"{world}_component_type.o",
            "-o",
            str(intermediate),
            "-mexec-model=reactor",
        ]
    else:
        raise ValueError(f"Unsupported lang: {lang}")

    return cmd, args

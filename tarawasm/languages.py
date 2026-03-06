from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple

from .config import LANG_CFGS, Config


def bind_args(
    lang: str,
    conf: Config,
    *,
    world_override: str | None = None,
    wit_override: Path | None = None,
) -> Tuple[List[str], List[str]]:
    cfg = LANG_CFGS[lang]
    wit_path = str(wit_override or conf.wit_path)
    world = world_override or conf.world
    wasm_file = conf.wasm_file

    if lang == "python":
        cmd = ["componentize-py"]
        args = [f"{cfg['wit-flag']}={wit_path}", f"--world={world}", "bindings", "."]
    elif lang == "go":
        cmd = ["go", "tool", "wit-bindgen-go"]
        args = ["generate", "--world", world, "-o", "internal", wit_path]
    elif lang == "js":
        cmd = ["jco", "guest-types"]
        args = ["-o", "internal", wit_path]
    elif lang == "rust":
        cmd = ["cargo", "component", "bindings"]
        args = []
    elif lang == "c":
        cmd = ["wit-bindgen", "c", wasm_file]
        args = []
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
) -> Tuple[List[str], List[str]]:
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
            src,
        ]
    elif lang == "js":
        cmd = ["jco", "componentize"]
        args = [
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
        args = ["--release"]
    elif lang == "c":
        cmd = ["clang", src, f"{world}.c", f"{world}_component_type.o"]
        args = ["-o", f"{world}.wasm", "-mexec-model=reactor"]
    else:
        raise ValueError(f"Unsupported lang: {lang}")

    return cmd, args

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from .config import LANG_CFGS, Config


def bind_args(lang: str, conf: Config) -> Tuple[List[str], List[str]]:
    cfg = LANG_CFGS[lang]
    wit_path = str(conf.wit_path)
    world = conf.world
    wasm_file = conf.wasm_file

    if lang == "python":
        cmd = ["componentize-py"]
        args = [f"{cfg['wit-flag']}={wit_path}", f"--world={world}", "bindings", "."]
    elif lang == "go":
        cmd = [
            "go",
            "run",
            "go.bytecodealliance.org/cmd/wit-bindgen-go",
            "generate",
        ]
        args = ["-o", "internal/", wit_path]
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


def build_args(lang: str, conf: Config) -> Tuple[List[str], List[str]]:
    cfg = LANG_CFGS[lang]
    world = conf.world
    src = conf.src_file
    wit_path = str(conf.wit_path)
    wasm_file = conf.wasm_file

    if lang == "python":
        cmd = ["componentize-py"]
        args = [
            f"{cfg['wit-flag']}={wit_path}",
            f"--world={world}",
            "componentize",
            Path(src).stem,
            "-o",
            f"{world}.wasm",
        ]
    elif lang == "go":
        cmd = ["tinygo", "build"]
        args = [
            f"-target={cfg['tinygo-target']}",
            "-o",
            f"{world}.wasm",
            "--wit-package",
            wasm_file,
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
            f"{world}.wasm",
            "--disable",
            "http",
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

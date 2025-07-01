from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from importlib.resources import as_file, files, read_text
from pathlib import Path

import click

CONFIG_FILE = "tarawasm.json"

LANG_CFGS = {
    "python": {"wit-flag": "--wit-path", "default-src": "main.py"},
    "go": {
        "wit-flag": "--wit-dir",
        "tinygo-target": "wasip2",
        "default-src": "main.go",
    },
    "js": {"wit-flag": "--wit", "default-src": "main.js"},
    "rust": {
        "default-src": "src/lib.rs",
        "cargo-component": "cargo",
        "release-target": "wasm32-wasip1",
    },
    "c": {
        "default-src": "component.c",
    },
}


class ConfigError(Exception):
    """Raised when configuration file is missing or invalid."""


@dataclass
class Config:
    world: str
    lang: str
    wit_path: Path
    src_file: str
    wasm_file: str

    @staticmethod
    def load() -> "Config":
        if not Path(CONFIG_FILE).exists():
            raise ConfigError(
                f"Config file '{CONFIG_FILE}' not found. Run 'init' first."
            )
        data = json.loads(Path(CONFIG_FILE).read_text())
        return Config(
            world=data["world"],
            lang=data["lang"],
            wit_path=Path(data["wit_path"]),
            src_file=data["src_file"],
            wasm_file=data["wasm_file"],
        )

    def save(self) -> None:
        data = {
            "world": self.world,
            "lang": self.lang,
            "wit_path": str(self.wit_path),
            "src_file": self.src_file,
            "wasm_file": self.wasm_file,
        }
        Path(CONFIG_FILE).write_text(json.dumps(data, indent=2))


def load_template(lang: str) -> str:
    return read_text("tarawasm.templates", f"{lang}.tpl")


def copy_runtime_wasm() -> None:
    dst_wasm = Path("wasi_snapshot_preview1.wasm")
    try:
        wasm_resource = files("tarawasm.lang_deps") / "wasi_snapshot_preview1.wasm"
        with as_file(wasm_resource) as src_wasm:
            shutil.copyfile(src_wasm, dst_wasm)
        click.echo(f"Copied runtime WASM to {dst_wasm}")
    except FileNotFoundError:
        raise click.ClickException(
            "Runtime file 'wasi_snapshot_preview1.wasm' not found in package."
        )

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from importlib.resources import as_file, files, read_text
from pathlib import Path
from typing import Any

import click

CONFIG_FILE = "tarawasm.json"
DEFAULT_STATE_DIR = ".tarawasm"
DEFAULT_DIST_DIR = "dist"

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
    "c": {"default-src": "component.c"},
}

_CONFIG_KEYS = {
    "world",
    "lang",
    "wit_path",
    "src_file",
    "wasm_file",
    "state_dir",
    "dist_dir",
}


class ConfigError(Exception):
    """Raised when a configuration file is missing or invalid."""


def discover_config(start: Path | str | None = None) -> Path:
    """Find tarawasm.json in *start* or one of its parents."""
    candidate = Path(start or Path.cwd()).expanduser()
    if candidate.name == CONFIG_FILE and candidate.is_file():
        return candidate.resolve()
    if candidate.is_file():
        candidate = candidate.parent
    candidate = candidate.resolve()
    for directory in (candidate, *candidate.parents):
        config_path = directory / CONFIG_FILE
        if config_path.is_file():
            return config_path
    raise ConfigError(
        f"Config file '{CONFIG_FILE}' not found in '{candidate}' or its parents. "
        "Run 'init' first."
    )


def _require_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Config field '{key}' must be a non-empty string.")
    return value


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _validate_managed_directory(path: Path, root: Path, key: str) -> None:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ConfigError(
            f"Config field '{key}' must stay inside the project root."
        ) from exc
    if relative == Path("."):
        raise ConfigError(f"Config field '{key}' cannot be the project root.")


@dataclass
class Config:
    world: str
    lang: str
    wit_path: Path
    src_file: str
    wasm_file: str
    state_dir: Path = Path(DEFAULT_STATE_DIR)
    dist_dir: Path = Path(DEFAULT_DIST_DIR)
    config_path: Path | None = field(default=None, repr=False, compare=False)

    @property
    def project_root(self) -> Path:
        return self.config_path.parent if self.config_path else Path.cwd().resolve()

    def resolve_path(self, path: Path | str) -> Path:
        value = Path(path).expanduser()
        if value.is_absolute():
            return value.resolve()
        return (self.project_root / value).resolve()

    @classmethod
    def load(cls, start: Path | str | None = None) -> Config:
        config_path = discover_config(start)
        try:
            data = json.loads(config_path.read_text())
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"Invalid JSON in '{config_path}': {exc.msg} at line {exc.lineno}."
            ) from exc
        except OSError as exc:
            raise ConfigError(f"Cannot read '{config_path}': {exc}.") from exc

        if not isinstance(data, dict):
            raise ConfigError("Config root must be a JSON object.")
        unknown = sorted(set(data) - _CONFIG_KEYS)
        missing = sorted(_CONFIG_KEYS - set(data))
        if unknown:
            raise ConfigError(f"Unknown config field(s): {', '.join(unknown)}.")
        if missing:
            raise ConfigError(f"Missing config field(s): {', '.join(missing)}.")

        world = _require_string(data, "world")
        lang = _require_string(data, "lang")
        if lang not in LANG_CFGS:
            raise ConfigError(
                f"Unsupported language '{lang}'; expected one of: "
                f"{', '.join(LANG_CFGS)}."
            )
        root = config_path.parent

        def resolved(key: str, default: str | None = None) -> Path:
            raw = data.get(key, default)
            if not isinstance(raw, str) or not raw.strip():
                raise ConfigError(f"Config field '{key}' must be a non-empty string.")
            path = Path(raw).expanduser()
            return path.resolve() if path.is_absolute() else (root / path).resolve()

        state_dir = resolved("state_dir")
        dist_dir = resolved("dist_dir")
        _validate_managed_directory(state_dir, root, "state_dir")
        _validate_managed_directory(dist_dir, root, "dist_dir")
        if state_dir == dist_dir:
            raise ConfigError("Config fields 'state_dir' and 'dist_dir' must differ.")

        conf = cls(
            world=world,
            lang=lang,
            wit_path=resolved("wit_path"),
            src_file=str(resolved("src_file")),
            wasm_file=str(resolved("wasm_file")),
            state_dir=state_dir,
            dist_dir=dist_dir,
            config_path=config_path,
        )
        return conf

    def save(self, path: Path | str | None = None) -> None:
        config_path = Path(path) if path is not None else self.config_path
        if config_path is None:
            config_path = Path.cwd() / CONFIG_FILE
        if not config_path.is_absolute():
            config_path = (Path.cwd() / config_path).resolve()
        root = config_path.parent
        resolved_state_dir = self.resolve_path(self.state_dir)
        resolved_dist_dir = self.resolve_path(self.dist_dir)
        _validate_managed_directory(resolved_state_dir, root, "state_dir")
        _validate_managed_directory(resolved_dist_dir, root, "dist_dir")
        if resolved_state_dir == resolved_dist_dir:
            raise ConfigError("Config fields 'state_dir' and 'dist_dir' must differ.")
        data = {
            "world": self.world,
            "lang": self.lang,
            "wit_path": _relative_or_absolute(self.resolve_path(self.wit_path), root),
            "src_file": _relative_or_absolute(self.resolve_path(self.src_file), root),
            "wasm_file": _relative_or_absolute(self.resolve_path(self.wasm_file), root),
            "state_dir": _relative_or_absolute(resolved_state_dir, root),
            "dist_dir": _relative_or_absolute(resolved_dist_dir, root),
        }
        root.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{CONFIG_FILE}.", dir=root, text=True
        )
        try:
            with os.fdopen(fd, "w") as temporary:
                json.dump(data, temporary, indent=2)
                temporary.write("\n")
            os.replace(temporary_name, config_path)
        except Exception:
            Path(temporary_name).unlink(missing_ok=True)
            raise
        self.config_path = config_path


def load_template(lang: str) -> str:
    return read_text("tarawasm.templates", f"{lang}.tpl")


def copy_runtime_wasm(destination: Path | str = "wasi_snapshot_preview1.wasm") -> Path:
    dst_wasm = Path(destination)
    dst_wasm.parent.mkdir(parents=True, exist_ok=True)
    try:
        wasm_resource = files("tarawasm.lang_deps") / "wasi_snapshot_preview1.wasm"
        with as_file(wasm_resource) as src_wasm:
            shutil.copyfile(src_wasm, dst_wasm)
        click.echo(f"Copied runtime WASM to {dst_wasm}")
        return dst_wasm
    except FileNotFoundError as exc:
        raise click.ClickException(
            "Runtime file 'wasi_snapshot_preview1.wasm' not found in package."
        ) from exc

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_FILE = "tarawasm.json"
STATE_DIR = Path(".tarawasm")
BUILD_DIR = STATE_DIR / "build"
IMPORTED_WIT_DIR = STATE_DIR / "imported-wit"
DEFAULT_DIST_DIR = Path("dist")
SUPPORTED_LANGUAGES = ("python", "go", "js", "rust", "c")

_CONFIG_KEYS = {"language", "world", "wit", "source", "output"}
_WIT_KEYS = {"path", "package"}


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
        "Run `tarawasm init` or `tarawasm import` first."
    )


def _require_string(data: dict[str, Any], key: str, prefix: str = "") -> str:
    value = data.get(key)
    field_name = f"{prefix}.{key}" if prefix else key
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Config field '{field_name}' must be a non-empty string.")
    return value


def _relative_or_absolute(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


@dataclass
class Config:
    language: str
    world: str
    wit_path: Path
    wit_package: str
    source: Path
    output: Path
    config_path: Path | None = field(default=None, repr=False, compare=False)

    @property
    def project_root(self) -> Path:
        return self.config_path.parent if self.config_path else Path.cwd().resolve()

    @property
    def state_dir(self) -> Path:
        return self.project_root / STATE_DIR

    @property
    def build_dir(self) -> Path:
        return self.project_root / BUILD_DIR

    @property
    def lang(self) -> str:
        """The configured backend name."""
        return self.language

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

        language = _require_string(data, "language")
        if language not in SUPPORTED_LANGUAGES:
            raise ConfigError(
                f"Config field 'language' has unsupported value '{language}'; "
                f"expected one of: {', '.join(SUPPORTED_LANGUAGES)}."
            )
        world = _require_string(data, "world")
        source = _require_string(data, "source")
        output = _require_string(data, "output")

        wit = data.get("wit")
        if not isinstance(wit, dict):
            raise ConfigError("Config field 'wit' must be an object.")
        wit_unknown = sorted(set(wit) - _WIT_KEYS)
        wit_missing = sorted(_WIT_KEYS - set(wit))
        if wit_unknown:
            raise ConfigError(
                f"Unknown config field(s): {', '.join(f'wit.{x}' for x in wit_unknown)}."
            )
        if wit_missing:
            raise ConfigError(
                f"Missing config field(s): {', '.join(f'wit.{x}' for x in wit_missing)}."
            )
        wit_path = _require_string(wit, "path", "wit")
        wit_package = _require_string(wit, "package", "wit")

        conf = cls(
            language=language,
            world=world,
            wit_path=Path(wit_path),
            wit_package=wit_package,
            source=Path(source),
            output=Path(output),
            config_path=config_path,
        )
        # Resolve here to make malformed path values fail close to their fields.
        for key, value in (
            ("wit.path", conf.wit_path),
            ("source", conf.source),
            ("output", conf.output),
        ):
            try:
                conf.resolve_path(value)
            except (OSError, RuntimeError, ValueError) as exc:
                raise ConfigError(
                    f"Config field '{key}' has an invalid path: {exc}."
                ) from exc
        return conf

    def save(self, path: Path | str | None = None) -> None:
        if self.language not in SUPPORTED_LANGUAGES:
            raise ConfigError(f"Unsupported language '{self.language}'.")
        config_path = Path(path) if path is not None else self.config_path
        if config_path is None:
            config_path = Path.cwd() / CONFIG_FILE
        if not config_path.is_absolute():
            config_path = (Path.cwd() / config_path).resolve()
        root = config_path.parent
        data = {
            "language": self.language,
            "world": self.world,
            "wit": {
                "path": _relative_or_absolute(self.resolve_path(self.wit_path), root),
                "package": self.wit_package,
            },
            "source": _relative_or_absolute(self.resolve_path(self.source), root),
            "output": _relative_or_absolute(self.resolve_path(self.output), root),
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

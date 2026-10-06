from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from .catalog import LANGUAGES, tools_for

LOCAL_FILE = "tarawasm.local.json"
LOCK_FILE = "tarawasm.toolchain.lock.json"


class ToolchainError(Exception):
    pass


def config_home() -> Path:
    explicit = os.environ.get("TARAWASM_CONFIG_HOME")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/tarawasm"
    return (
        Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        / "tarawasm"
    )


def data_home() -> Path:
    explicit = os.environ.get("TARAWASM_DATA_HOME")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/tarawasm/toolchains"
    return (
        Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        / "tarawasm/toolchains"
    )


def read_settings(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "languages": {}}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ToolchainError(f"Cannot read toolchain settings '{path}': {exc}") from exc
    if not isinstance(data, dict) or set(data) != {"schema_version", "languages"}:
        raise ToolchainError(f"Invalid toolchain settings '{path}'.")
    if data["schema_version"] != 1 or not isinstance(data["languages"], dict):
        raise ToolchainError(f"Unsupported toolchain settings '{path}'.")
    for language, profile in data["languages"].items():
        validate_profile(language, profile)
    return data


def validate_profile(language: str, profile: dict) -> None:
    if language not in LANGUAGES or not isinstance(profile, dict):
        raise ToolchainError("Invalid toolchain language/profile.")
    if set(profile) - {"mode", "image", "platform", "tools", "versions"}:
        raise ToolchainError("Unknown toolchain profile field.")
    if profile.get("mode") not in {"local", "docker"}:
        raise ToolchainError("Toolchain mode must be local or docker.")
    for key in ("image", "platform"):
        value = profile.get(key)
        if value is not None and (
            not isinstance(value, str)
            or not value
            or value.startswith("-")
            or any(c.isspace() for c in value)
        ):
            raise ToolchainError(f"Invalid toolchain {key}.")
    for key in ("tools", "versions"):
        values = profile.get(key, {})
        if not isinstance(values, dict):
            raise ToolchainError(f"Toolchain {key} must be an object.")
        for name, value in values.items():
            if (
                name not in tools_for(language)
                or not isinstance(value, str)
                or not value
            ):
                raise ToolchainError(f"Invalid {key} entry: {name}.")
            if key == "tools" and not Path(value).is_absolute():
                raise ToolchainError(f"Tool path must be absolute: {name}.")


def write_settings(path: Path, data: dict) -> None:
    # Validate before touching the filesystem, and replace only our settings file.
    if data.get("schema_version") != 1:
        raise ToolchainError("Unsupported toolchain settings schema.")
    for language, profile in data["languages"].items():
        validate_profile(language, profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def selected_profile(
    language: str,
    root: Path | None = None,
    *,
    mode: str | None = None,
    image: str | None = None,
) -> tuple[dict | None, str]:
    global_path = config_home() / "settings.json"
    profile = read_settings(global_path)["languages"].get(language)
    source = str(global_path) if profile else "discovery"
    if root:
        local = read_settings(root / LOCAL_FILE)["languages"].get(language)
        if local:
            profile, source = local, str(root / LOCAL_FILE)
    if mode:
        profile = {**(profile or {}), "mode": mode}
        if mode == "docker":
            profile.pop("tools", None)
        else:
            profile.pop("image", None)
            profile.pop("platform", None)
    if image:
        profile = {**(profile or {"mode": "docker"}), "image": image}
    if root:
        locked = read_settings(root / LOCK_FILE)["languages"].get(language)
        if locked:
            source = str(root / LOCK_FILE) if source == "discovery" else source
            # A lock constrains versions; it does not choose the execution mode.
            profile = dict(profile or {"mode": "local"})
            if profile["mode"] == "docker" and locked.get("image"):
                if image and image != locked["image"]:
                    raise ToolchainError(
                        "Explicit image differs from the project lock. Update the lock before changing its image."
                    )
                profile["image"] = locked["image"]
                profile["platform"] = locked.get("platform", "linux/amd64")
            profile["versions"] = locked.get("versions", {})
    return profile, source


def save_profile(language: str, profile: dict, root: Path | None = None) -> None:
    path = root / LOCAL_FILE if root else config_home() / "settings.json"
    data = read_settings(path)
    data["languages"][language] = profile
    write_settings(path, data)

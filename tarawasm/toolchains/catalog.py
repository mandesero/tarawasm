from __future__ import annotations

import json
import re
from importlib.resources import files

from tarawasm.config import SUPPORTED_LANGUAGES

CATALOG = json.loads(
    (files("tarawasm.toolchains") / "catalog.json").read_text(encoding="utf-8")
)
TOOLS: dict[str, dict] = CATALOG["tools"]
LANGUAGES = SUPPORTED_LANGUAGES


def tools_for(language: str) -> tuple[str, ...]:
    return tuple(name for name, spec in TOOLS.items() if language in spec["languages"])


def version_tuple(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)(?:\.(\d+))?", value)
    if not match:
        raise ValueError(f"Unsupported version: {value}")
    return tuple(int(item or 0) for item in match.groups())  # type: ignore[return-value]


def version_status(name: str, value: str) -> str:
    spec = TOOLS[name]
    found = version_tuple(value)
    if found < version_tuple(spec["minimum"]):
        return "outdated"
    maximum = spec.get("maximum_exclusive")
    if maximum and found >= version_tuple(maximum):
        return "incompatible"
    return "ready"


def supported_range(name: str) -> str:
    spec = TOOLS[name]
    result = f">={spec['minimum']}"
    if spec.get("maximum_exclusive"):
        result += f",<{spec['maximum_exclusive']}"
    return result


def default_image(language: str) -> str:
    return f"mandeser0/tarawasm:{CATALOG['image_release']}-{language}"

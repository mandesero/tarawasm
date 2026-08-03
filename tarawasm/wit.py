from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class WitError(Exception):
    """A WIT document could not be parsed or selected."""


@dataclass(frozen=True)
class WitType:
    kind: str
    name: str | None = None
    value: Any = None


@dataclass(frozen=True)
class WitParam:
    name: str
    type: WitType


@dataclass(frozen=True)
class WitFunction:
    name: str
    kind: str
    params: tuple[WitParam, ...]
    result: WitType | None
    resource: str | None = None


@dataclass(frozen=True)
class WitInterface:
    name: str
    functions: tuple[WitFunction, ...]
    types: tuple[WitType, ...]
    package: str


@dataclass(frozen=True)
class WitItem:
    name: str
    kind: str
    function: WitFunction | None = None
    interface: WitInterface | None = None
    type: WitType | None = None


@dataclass(frozen=True)
class WitWorld:
    name: str
    package: str
    imports: tuple[WitItem, ...]
    exports: tuple[WitItem, ...]


@dataclass(frozen=True)
class WitDocument:
    path: Path
    packages: tuple[str, ...]
    worlds: tuple[WitWorld, ...]
    interfaces: tuple[WitInterface, ...]
    types: tuple[WitType, ...]

    def select_world(self, name: str | None) -> WitWorld:
        available = [world.name for world in self.worlds]
        if name is None:
            if len(self.worlds) == 1:
                return self.worlds[0]
            if not self.worlds:
                raise WitError(f"WIT '{self.path}' does not define a world.")
            raise WitError(
                f"WIT '{self.path}' defines multiple worlds: {', '.join(available)}. "
                "Select one with --world."
            )
        matches = [world for world in self.worlds if world.name == name]
        if len(matches) == 1:
            return matches[0]
        raise WitError(
            f"World '{name}' was not found in WIT '{self.path}'. Available worlds: "
            f"{', '.join(available) if available else '(none)'}."
        )


class WitParser:
    """Structured adapter for `wasm-tools component wit --json`."""

    def __init__(self, executable: str = "wasm-tools") -> None:
        self.executable = executable

    def parse(self, path: Path | str) -> WitDocument:
        source = Path(path).expanduser().resolve()
        if not source.exists():
            raise WitError(f"WIT path '{source}' does not exist.")
        try:
            result = subprocess.run(
                [self.executable, "component", "wit", str(source), "--json"],
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise WitError(
                "Required tool 'wasm-tools' was not found. Install wasm-tools and retry."
            ) from exc
        if result.returncode != 0:
            reason = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise WitError(f"Invalid WIT at '{source}': {reason}")
        try:
            raw = json.loads(result.stdout)
            return self._decode(source, raw)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise WitError(
                f"Cannot decode structured WIT for '{source}': {exc}. "
                "Check that wasm-tools is a supported version."
            ) from exc

    def _decode(self, path: Path, raw: dict[str, Any]) -> WitDocument:
        raw_packages = raw["packages"]
        raw_types = raw["types"]
        raw_interfaces = raw["interfaces"]
        packages = tuple(str(package["name"]) for package in raw_packages)

        types: list[WitType] = []
        for type_id, entry in enumerate(raw_types):
            types.append(self._decode_type(entry, type_id, raw_types))

        interfaces: list[WitInterface] = []
        for entry in raw_interfaces:
            package = packages[int(entry["package"])]
            interface_types = tuple(types[int(i)] for i in entry["types"].values())
            functions = tuple(
                self._decode_function(function, types)
                for function in entry["functions"].values()
            )
            interfaces.append(
                WitInterface(
                    name=str(entry["name"]),
                    functions=functions,
                    types=interface_types,
                    package=package,
                )
            )

        worlds: list[WitWorld] = []
        for entry in raw["worlds"]:
            package = packages[int(entry["package"])]
            worlds.append(
                WitWorld(
                    name=str(entry["name"]),
                    package=package,
                    imports=tuple(
                        self._decode_world_item(name, item, types, interfaces)
                        for name, item in entry["imports"].items()
                    ),
                    exports=tuple(
                        self._decode_world_item(name, item, types, interfaces)
                        for name, item in entry["exports"].items()
                    ),
                )
            )
        return WitDocument(
            path, packages, tuple(worlds), tuple(interfaces), tuple(types)
        )

    def _decode_world_item(
        self,
        name: str,
        item: dict[str, Any],
        types: list[WitType],
        interfaces: list[WitInterface],
    ) -> WitItem:
        if "function" in item:
            return WitItem(
                name=name,
                kind="function",
                function=self._decode_function(item["function"], types),
            )
        if "interface" in item:
            interface = item["interface"]
            return WitItem(
                name=name,
                kind="interface",
                interface=interfaces[int(interface["id"])],
            )
        if "type" in item:
            return WitItem(
                name=name,
                kind="type",
                type=self._type_ref(item["type"], types),
            )
        raise ValueError(
            f"Unsupported world item '{name}'; expected function, interface, or type"
        )

    def _decode_function(
        self, entry: dict[str, Any], types: list[WitType]
    ) -> WitFunction:
        raw_kind = entry["kind"]
        resource: str | None = None
        if isinstance(raw_kind, str):
            kind = raw_kind
        else:
            kind, resource_id = next(iter(raw_kind.items()))
            resource = types[int(resource_id)].name
        params = tuple(
            WitParam(str(param["name"]), self._type_ref(param["type"], types))
            for param in entry["params"]
        )
        raw_result = entry.get("result")
        result = None if raw_result is None else self._type_ref(raw_result, types)
        return WitFunction(str(entry["name"]), kind, params, result, resource)

    def _type_ref(self, value: Any, types: list[WitType]) -> WitType:
        if isinstance(value, str):
            return WitType("primitive", name=value)
        return types[int(value)]

    def _decode_type(
        self, entry: dict[str, Any], type_id: int, raw_types: list[dict[str, Any]]
    ) -> WitType:
        name = entry.get("name")
        raw_kind = entry["kind"]
        if isinstance(raw_kind, str):
            return WitType(raw_kind, name=name)
        kind, payload = next(iter(raw_kind.items()))

        def ref(value: Any) -> WitType:
            if isinstance(value, str):
                return WitType("primitive", name=value)
            referenced = raw_types[int(value)]
            ref_name = referenced.get("name")
            if ref_name:
                nested_kind = referenced["kind"]
                nested_name = (
                    nested_kind
                    if isinstance(nested_kind, str)
                    else next(iter(nested_kind))
                )
                return WitType("alias", name=ref_name, value=nested_name)
            if int(value) == type_id:
                return WitType("recursive", name=name)
            return self._decode_type(referenced, int(value), raw_types)

        decoded_value: Any
        if kind == "record":
            decoded_value = tuple(
                (field["name"], ref(field["type"])) for field in payload["fields"]
            )
        elif kind == "tuple":
            decoded_value = tuple(ref(item) for item in payload["types"])
        elif kind in {"list", "option", "type"}:
            decoded_value = ref(payload)
        elif kind == "result":
            decoded_value = (
                None if payload["ok"] is None else ref(payload["ok"]),
                None if payload["err"] is None else ref(payload["err"]),
            )
        elif kind == "variant":
            decoded_value = tuple(
                (case["name"], None if case.get("type") is None else ref(case["type"]))
                for case in payload["cases"]
            )
        elif kind == "enum":
            decoded_value = tuple(case["name"] for case in payload["cases"])
        elif kind == "flags":
            decoded_value = tuple(flag["name"] for flag in payload["flags"])
        elif kind == "handle":
            handle_kind, resource_id = next(iter(payload.items()))
            decoded_value = (handle_kind, ref(resource_id))
        else:
            decoded_value = payload
        return WitType(kind, name=name, value=decoded_value)

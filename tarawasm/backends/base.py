from __future__ import annotations

import re
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from tarawasm.config import Config
from tarawasm.wit import WitWorld


class BackendError(Exception):
    """A language backend cannot perform a requested operation."""


@dataclass(frozen=True)
class Command:
    argv: tuple[str, ...]
    env: dict[str, str] = field(default_factory=dict)


def snake(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()


def pascal(name: str) -> str:
    return "".join(part.capitalize() for part in snake(name).split("_") if part)


def upper_snake(name: str) -> str:
    return snake(name).upper()


class LanguageBackend(ABC):
    name: str
    default_source: Path
    required_tools: tuple[str, ...]

    def doctor(self) -> list[str]:
        return [tool for tool in self.required_tools if shutil.which(tool) is None]

    def validate_world(self, world: WitWorld) -> None:
        """Reject WIT shapes the backend toolchain cannot build."""

    def initialize_files(
        self, world: WitWorld, wit_path: Path, project_root: Path
    ) -> dict[Path, str | bytes]:
        return {self.default_source: self.generate_source(world)}

    @abstractmethod
    def generate_source(self, world: WitWorld) -> str:
        pass

    @abstractmethod
    def bind_command(
        self,
        conf: Config,
        *,
        world: str,
        wit: Path,
        tool_args: list[str],
    ) -> Command:
        pass

    def bind_commands(
        self,
        conf: Config,
        *,
        world: str,
        wit: Path,
        tool_args: list[str],
    ) -> tuple[Command, ...]:
        return (self.bind_command(conf, world=world, wit=wit, tool_args=tool_args),)

    @abstractmethod
    def build_command(
        self,
        conf: Config,
        *,
        world: str,
        wit: Path,
        source: Path,
        output: Path,
        tool_args: list[str],
    ) -> Command:
        pass

    def locate_artifact(self, conf: Config, requested: Path) -> Path:
        return requested

    def finish_build_command(
        self, conf: Config, *, world: str, output: Path
    ) -> Command | None:
        return None

    def generated_artifacts(self, conf: Config) -> tuple[Path, ...]:
        return ()

from __future__ import annotations

import json
import os
from pathlib import Path

MANIFEST_NAME = "artifacts.json"


class ArtifactManifest:
    """Tracks only paths created by tarawasm commands."""

    def __init__(self, project_root: Path, state_dir: Path) -> None:
        self.project_root = project_root.resolve()
        self.state_dir = state_dir.resolve()
        self.path = self.state_dir / MANIFEST_NAME

    def snapshot(self) -> set[str]:
        result: set[str] = set()
        for root, dirs, files in os.walk(self.project_root):
            root_path = Path(root)
            dirs[:] = [name for name in dirs if name != ".git"]
            for name in [*dirs, *files]:
                path = root_path / name
                if path == self.path:
                    continue
                result.add(path.relative_to(self.project_root).as_posix())
        return result

    def _load(self) -> set[str]:
        if not self.path.exists():
            return set()
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return set()
        artifacts = data.get("artifacts", []) if isinstance(data, dict) else []
        return {
            item
            for item in artifacts
            if isinstance(item, str) and self._safe_path(item) is not None
        }

    def _safe_path(self, relative: str) -> Path | None:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or path == Path("."):
            return None
        resolved = (self.project_root / path).resolve()
        try:
            resolved.relative_to(self.project_root)
        except ValueError:
            return None
        if resolved in (self.project_root, self.state_dir, self.path):
            return None
        return resolved

    def record_created_since(self, before: set[str]) -> None:
        created = self.snapshot() - before
        if not created:
            return
        artifacts = self._load() | created
        self.state_dir.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, "artifacts": sorted(artifacts)}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n")
        os.replace(temporary, self.path)

    def clean(self) -> list[str]:
        removed: list[str] = []
        artifacts = self._load()
        for relative in sorted(
            artifacts, key=lambda item: (len(Path(item).parts), item), reverse=True
        ):
            path = self._safe_path(relative)
            if path is None or not path.exists() and not path.is_symlink():
                continue
            if path.is_dir() and not path.is_symlink():
                try:
                    path.rmdir()
                except OSError:
                    continue
            else:
                path.unlink()
            removed.append(relative)
        if self.path.exists():
            self.path.unlink()
        try:
            self.state_dir.rmdir()
        except OSError:
            pass
        return removed

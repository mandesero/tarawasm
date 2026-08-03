from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

import click

from tarawasm.artifacts import ArtifactManifest
from tarawasm.backends import BackendError, backend_names, get_backend
from tarawasm.backends.base import Command
from tarawasm.config import (
    CONFIG_FILE,
    IMPORTED_WIT_DIR,
    Config,
    ConfigError,
)
from tarawasm.wit import WitError, WitParser


@contextmanager
def _project_directory(conf: Config):
    previous = Path.cwd()
    os.chdir(conf.project_root)
    try:
        yield
    finally:
        os.chdir(previous)


def _fail(error: Exception) -> click.ClickException:
    return click.ClickException(str(error))


def _run(command: Command, *, dry_run: bool = False, check: bool = True) -> None:
    click.echo(f"Running: {shlex.join(command.argv)}")
    if dry_run:
        return
    environment = os.environ.copy()
    environment.update(command.env)
    try:
        subprocess.run(command.argv, check=check, env=environment)
    except FileNotFoundError as exc:
        raise click.ClickException(
            f"Required tool '{command.argv[0]}' was not found."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(
            f"Command failed with exit code {exc.returncode}: {shlex.join(command.argv)}"
        ) from exc


def _validate_tool_args(tool_args: list[str], common_options: set[str]) -> None:
    for token in tool_args:
        option = token.split("=", 1)[0]
        if token.startswith("-") and option in common_options:
            raise click.ClickException(
                f"Common option '{option}' must be provided before '--'."
            )


def _parse_selected_world(wit: Path, world: str):
    try:
        return WitParser().parse(wit).select_world(world)
    except WitError as exc:
        raise _fail(exc)


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _config_bytes(conf: Config, root: Path) -> bytes:
    data = {
        "language": conf.language,
        "world": conf.world,
        "wit": {
            "path": _relative_or_absolute(conf.resolve_path(conf.wit_path), root),
            "package": conf.wit_package,
        },
        "source": _relative_or_absolute(conf.resolve_path(conf.source), root),
        "output": _relative_or_absolute(conf.resolve_path(conf.output), root),
    }
    return (json.dumps(data, indent=2) + "\n").encode()


def _install_project_files(
    root: Path,
    files: dict[Path, str | bytes],
    *,
    force: bool,
    sources: set[Path],
) -> None:
    conflicts = sorted(path for path in files if (root / path).exists())
    protected_source = any(source in conflicts for source in sources)
    if conflicts and (not force or protected_source):
        rendered = ", ".join(path.as_posix() for path in conflicts)
        suffix = (
            " Existing source files are never overwritten."
            if protected_source
            else " Use --force to replace known generated project files."
        )
        raise click.ClickException(f"Project file conflict(s): {rendered}.{suffix}")

    root.parent.mkdir(parents=True, exist_ok=True)
    staging_parent = root if root.exists() else root.parent
    with tempfile.TemporaryDirectory(
        prefix=".tarawasm-init-", dir=staging_parent
    ) as temporary:
        staging = Path(temporary) / "new"
        backup = Path(temporary) / "backup"
        for relative, content in files.items():
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                destination.write_bytes(content)
            else:
                destination.write_text(content)
        if not root.exists():
            os.replace(staging, root)
            return
        installed: list[Path] = []
        backed_up: list[Path] = []
        try:
            for relative in files:
                destination = root / relative
                if destination.exists():
                    saved = backup / relative
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(destination, saved)
                    backed_up.append(relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staging / relative, destination)
                installed.append(relative)
        except Exception:
            for relative in reversed(installed):
                (root / relative).unlink(missing_ok=True)
            for relative in reversed(backed_up):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(backup / relative, destination)
            raise


@click.group()
def cli() -> None:
    """Build WebAssembly components from WIT contracts."""


@cli.command()
@click.option(
    "--lang", "language", "-l", required=True, type=click.Choice(backend_names())
)
@click.option(
    "--wit",
    "wit_path",
    required=True,
    type=click.Path(path_type=Path, exists=True),
    help="WIT file or package directory.",
)
@click.option("--world", help="World to implement; inferred when WIT has one world.")
@click.option("--force", is_flag=True, help="Replace known generated project files.")
@click.option(
    "--dry-run", is_flag=True, help="Validate and show files without writing."
)
@click.argument("project_dir", type=click.Path(path_type=Path), default=Path("."))
def init(
    language: str,
    wit_path: Path,
    world: str | None,
    force: bool,
    dry_run: bool,
    project_dir: Path,
) -> None:
    """Create a project directly from a WIT contract."""
    try:
        document = WitParser().parse(wit_path)
        selected = document.select_world(world)
        backend = get_backend(language)
    except (WitError, BackendError) as exc:
        raise _fail(exc)

    root = project_dir.expanduser().resolve()
    source = backend.default_source
    output = Path("dist") / f"{selected.name}.wasm"
    conf = Config(
        language=language,
        world=selected.name,
        wit_path=wit_path.resolve(),
        wit_package=selected.package,
        source=source,
        output=output,
        config_path=root / CONFIG_FILE,
    )
    try:
        files = backend.initialize_files(selected, wit_path.resolve(), root)
    except (BackendError, OSError) as exc:
        raise _fail(exc)
    files[Path(CONFIG_FILE)] = _config_bytes(conf, root)
    click.echo(
        f"Project: {root}\nLanguage: {language}\n"
        f"WIT package: {selected.package}\nWorld: {selected.name}"
    )
    for relative in sorted(files):
        click.echo(f"  create {relative.as_posix()}")
    if dry_run:
        click.echo("Dry run: no files were created.")
        return
    source_paths = {
        path
        for path in files
        if path.suffix in {".py", ".go", ".js", ".rs", ".c", ".cc", ".cpp"}
    }
    _install_project_files(root, files, force=force, sources=source_paths)
    click.echo(f"Configuration saved to '{root / CONFIG_FILE}'.")


@cli.command(name="import")
@click.option(
    "--lang", "language", "-l", required=True, type=click.Choice(backend_names())
)
@click.option(
    "--component",
    required=True,
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    help="Existing WebAssembly component to import.",
)
@click.option(
    "--world", help="World to implement; inferred when the component has one."
)
@click.option("--force", is_flag=True, help="Replace known generated project files.")
@click.option(
    "--dry-run", is_flag=True, help="Validate and show files without writing."
)
@click.argument("project_dir", type=click.Path(path_type=Path), default=Path("."))
def import_component(
    language: str,
    component: Path,
    world: str | None,
    force: bool,
    dry_run: bool,
    project_dir: Path,
) -> None:
    """Create a project by importing an existing WebAssembly component."""
    root = project_dir.expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix="tarawasm-import-") as temporary:
        extracted = Path(temporary) / "wit"
        try:
            result = subprocess.run(
                (
                    "wasm-tools",
                    "component",
                    "wit",
                    str(component.resolve()),
                    "--out-dir",
                    str(extracted),
                ),
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise click.ClickException(
                "Required tool 'wasm-tools' was not found."
            ) from exc
        if result.returncode != 0:
            reason = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise click.ClickException(
                f"'{component}' is not a WebAssembly Component Model binary: {reason}"
            )
        try:
            document = WitParser().parse(extracted)
            selected = document.select_world(world)
            backend = get_backend(language)
        except (WitError, BackendError) as exc:
            raise _fail(exc)

        final_wit = root / IMPORTED_WIT_DIR
        conf = Config(
            language=language,
            world=selected.name,
            wit_path=final_wit,
            wit_package=selected.package,
            source=backend.default_source,
            output=Path("dist") / f"{selected.name}.wasm",
            config_path=root / CONFIG_FILE,
        )
        try:
            files = backend.initialize_files(selected, final_wit, root)
        except (BackendError, OSError) as exc:
            raise _fail(exc)
        for source_file in extracted.rglob("*"):
            if source_file.is_file():
                relative = source_file.relative_to(extracted)
                if relative.parent == Path("deps") and relative.suffix == ".wit":
                    relative = relative.parent / relative.stem / "package.wit"
                files[IMPORTED_WIT_DIR / relative] = source_file.read_bytes()
        files[Path(CONFIG_FILE)] = _config_bytes(conf, root)

        click.echo(
            f"Project: {root}\nLanguage: {language}\n"
            f"Imported component: {component.resolve()}\n"
            f"WIT package: {selected.package}\nWorld: {selected.name}"
        )
        for relative in sorted(files):
            click.echo(f"  create {relative.as_posix()}")
        if dry_run:
            click.echo("Dry run: no files were created.")
            return
        source_paths = {
            path
            for path in files
            if path.suffix in {".py", ".go", ".js", ".rs", ".c", ".cc", ".cpp"}
            and IMPORTED_WIT_DIR not in path.parents
        }
        _install_project_files(root, files, force=force, sources=source_paths)
    click.echo(f"Configuration saved to '{root / CONFIG_FILE}'.")


@cli.command()
def clean() -> None:
    """Remove only artifacts tracked by tarawasm."""
    try:
        conf = Config.load()
    except ConfigError as exc:
        raise _fail(exc)
    removed = ArtifactManifest(conf.project_root, conf.state_dir).clean()
    click.echo(
        f"Removed {len(removed)} tracked artifact(s) for "
        f"{conf.language} world '{conf.world}'."
    )


@cli.group()
def deps() -> None:
    """Manage reproducible WIT dependencies with wkg."""


def _dependency_paths(conf: Config) -> tuple[Path, Path, Path]:
    wit = conf.resolve_path(conf.wit_path)
    wit_dir = wit if wit.is_dir() else wit.parent
    return wit_dir, wit_dir / "wkg.lock", conf.state_dir / "deps/cache"


def _run_dependency_command(action: str, *, dry_run: bool) -> None:
    try:
        conf = Config.load()
    except ConfigError as exc:
        raise _fail(exc)
    wit_dir, lock, cache = _dependency_paths(conf)
    command = Command(
        (
            "wkg",
            "wit",
            action,
            "--wit-dir",
            str(wit_dir),
            "--cache",
            str(cache),
        )
    )
    if dry_run:
        _run(command, dry_run=True)
        return
    cache.mkdir(parents=True, exist_ok=True)
    previous_lock = lock.read_bytes() if lock.is_file() else None
    _run(command)
    if action == "fetch" and previous_lock is not None:
        current_lock = lock.read_bytes() if lock.is_file() else None
        if current_lock != previous_lock:
            lock.write_bytes(previous_lock)
            raise click.ClickException(
                "WIT dependencies differ from wkg.lock. "
                "Run `tarawasm deps update` to update them explicitly."
            )


@deps.command(name="resolve")
@click.option("--dry-run", is_flag=True)
def deps_resolve(dry_run: bool) -> None:
    """Fetch dependencies pinned by wkg.lock, or create the initial lock."""
    _run_dependency_command("fetch", dry_run=dry_run)


@deps.command(name="update")
@click.option("--dry-run", is_flag=True)
def deps_update(dry_run: bool) -> None:
    """Explicitly update dependencies and wkg.lock."""
    _run_dependency_command("update", dry_run=dry_run)


@deps.command(name="list")
def deps_list() -> None:
    """List packages pinned in wkg.lock."""
    try:
        conf = Config.load()
    except ConfigError as exc:
        raise _fail(exc)
    _, lock, _ = _dependency_paths(conf)
    if not lock.is_file():
        raise click.ClickException(
            f"Dependency lock '{lock}' does not exist. Run `tarawasm deps resolve`."
        )
    text = lock.read_text()
    packages = re.findall(r'name\s*=\s*"([^"]+)"[\s\S]*?version\s*=\s*"([^"]+)"', text)
    if not packages:
        click.echo("No locked WIT dependencies.")
        return
    for name, version in packages:
        click.echo(f"{name}@{version}")


@cli.command()
@click.option("--world", help="Override the configured world for this run.")
@click.option("--wit", "wit_path", type=click.Path(path_type=Path))
@click.option("--tool-help", is_flag=True)
@click.option("--dry-run", is_flag=True)
@click.argument("tool_args", nargs=-1, type=click.UNPROCESSED)
def bind(
    world: str | None,
    wit_path: Path | None,
    tool_help: bool,
    dry_run: bool,
    tool_args: tuple[str, ...],
) -> None:
    """Generate language bindings from WIT."""
    _validate_tool_args(
        list(tool_args), {"--world", "--wit", "--tool-help", "--dry-run"}
    )
    try:
        conf = Config.load()
        backend = get_backend(conf.language)
    except (ConfigError, BackendError) as exc:
        raise _fail(exc)
    resolved_world = world or conf.world
    resolved_wit = conf.resolve_path(wit_path or conf.wit_path)
    _parse_selected_world(resolved_wit, resolved_world)
    commands = backend.bind_commands(
        conf,
        world=resolved_world,
        wit=resolved_wit,
        tool_args=list(tool_args),
    )
    if tool_help:
        command = commands[-1]
        _run(Command((*command.argv, "--help"), command.env), check=False)
        return
    with _project_directory(conf):
        manifest = ArtifactManifest(conf.project_root, conf.state_dir)
        before = manifest.snapshot()
        try:
            for command in commands:
                _run(command, dry_run=dry_run)
        finally:
            if not dry_run:
                manifest.record_created_since(before)


@cli.command()
@click.option("--world", help="Override the configured world for this run.")
@click.option("--wit", "wit_path", type=click.Path(path_type=Path))
@click.option("--src", "source", type=click.Path(path_type=Path))
@click.option("--out", "output", type=click.Path(path_type=Path))
@click.option("--clean", "run_clean", is_flag=True)
@click.option("--tool-help", is_flag=True)
@click.option("--dry-run", is_flag=True)
@click.argument("tool_args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def build(
    ctx: click.Context,
    world: str | None,
    wit_path: Path | None,
    source: Path | None,
    output: Path | None,
    run_clean: bool,
    tool_help: bool,
    dry_run: bool,
    tool_args: tuple[str, ...],
) -> None:
    """Build and atomically publish a verified WebAssembly component."""
    _validate_tool_args(
        list(tool_args),
        {"--world", "--wit", "--src", "--out", "--clean", "--tool-help", "--dry-run"},
    )
    try:
        conf = Config.load()
        backend = get_backend(conf.language)
    except (ConfigError, BackendError) as exc:
        raise _fail(exc)
    resolved_world = world or conf.world
    resolved_wit = conf.resolve_path(wit_path or conf.wit_path)
    resolved_source = conf.resolve_path(source or conf.source)
    resolved_output = conf.resolve_path(output or conf.output)
    selected_world = _parse_selected_world(resolved_wit, resolved_world)
    try:
        backend.validate_world(selected_world)
    except BackendError as exc:
        raise _fail(exc)
    temporary_output = conf.build_dir / "publish" / f"{resolved_world}.wasm"
    command = backend.build_command(
        conf,
        world=resolved_world,
        wit=resolved_wit,
        source=resolved_source,
        output=temporary_output,
        tool_args=list(tool_args),
    )
    if tool_help:
        _run(Command((*command.argv, "--help"), command.env), check=False)
        return
    if run_clean and not dry_run:
        ctx.invoke(clean)
    with _project_directory(conf):
        manifest = ArtifactManifest(conf.project_root, conf.state_dir)
        before = manifest.snapshot()
        if dry_run:
            _run(command, dry_run=True)
            finish = backend.finish_build_command(
                conf, world=resolved_world, output=temporary_output
            )
            if finish:
                _run(finish, dry_run=True)
            click.echo(f"Would publish verified component to {resolved_output}")
            return
        temporary_output.parent.mkdir(parents=True, exist_ok=True)
        temporary_output.unlink(missing_ok=True)
        try:
            _run(command)
            finish = backend.finish_build_command(
                conf, world=resolved_world, output=temporary_output
            )
            if finish:
                _run(finish)
            built = backend.locate_artifact(conf, temporary_output)
            if built != temporary_output:
                if not built.is_file():
                    raise click.ClickException(
                        f"Build artifact '{built}' was not created."
                    )
                shutil.copyfile(built, temporary_output)
            if not temporary_output.is_file():
                raise click.ClickException(
                    f"Build did not create expected artifact '{temporary_output}'."
                )
            try:
                WitParser().parse(temporary_output)
            except WitError as exc:
                raise click.ClickException(
                    f"Build output is not a valid WebAssembly component: {exc}"
                ) from exc
            resolved_output.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary_output, resolved_output)
            manifest.record(resolved_output)
            click.echo(f"Built {resolved_output}")
        finally:
            manifest.record_created_since(before)


@cli.command(
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    add_help_option=False,
)
@click.argument("wasm")
@click.pass_context
def strip(ctx: click.Context, wasm: str) -> None:
    """Remove custom sections from a WebAssembly file."""
    output_flag_present = any(arg in ctx.args for arg in ("--output", "-o"))
    default_output = (
        ["--output", f"{wasm.rsplit('.', 1)[0]}.strip.wasm"]
        if not output_flag_present
        else []
    )
    _run(Command(("wasm-tools", "strip", wasm, *default_output, *ctx.args)))


@cli.command(name="all")
@click.pass_context
def all_commands(ctx: click.Context) -> None:
    """Run clean, bind, and build."""
    ctx.invoke(clean)
    ctx.invoke(bind)
    ctx.invoke(build)
    conf = Config.load()
    click.echo(f"{conf.resolve_path(conf.output)} is ready")


if __name__ == "__main__":
    cli()

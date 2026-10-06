from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

import click

from tarawasm.config import ConfigError, discover_config

from .catalog import CATALOG, LANGUAGES, TOOLS, default_image, tools_for
from .discovery import discover_local, docker_available, inspect_profile
from .installer import execute, install_tools, installation_plan, prerequisite_commands
from .settings import (
    LOCK_FILE,
    ToolchainError,
    read_settings,
    save_profile,
    selected_profile,
    validate_profile,
    write_settings,
)


def project_root() -> Path | None:
    try:
        return discover_config().parent
    except ConfigError:
        return None


def interactive() -> bool:
    context = click.get_current_context(silent=True)
    disabled = context and context.find_root().params.get("non_interactive", False)
    return not disabled and sys.stdin.isatty() and sys.stdout.isatty()


def emit_reports(reports: list[dict], as_json: bool = False) -> None:
    if as_json:
        click.echo(json.dumps({"schema_version": 1, "reports": reports}, indent=2))
        return
    for report in reports:
        click.echo(
            f"{report['language']}: {report['mode']} ({report.get('source', 'discovery')})"
        )
        if report.get("image"):
            click.echo(f"  Image: {report['image']} ({report.get('status', '')})")
            click.echo(f"  Image ID: {report.get('image_id', 'not checked')}")
        if report.get("detail"):
            click.echo(f"  {report['detail']}")
        for row in report["tools"]:
            click.echo(
                f"  {row['tool']:<18} {row['mode']:<7} {row['version'] or '-':<12} {row['supported']:<20} {row['status']:<12} {row['location'] or '-'} ({row['detail']})"
            )


def report_for(language: str, root: Path | None = None) -> dict:
    if os.environ.get("INSIDE_DOCKER") == "1":
        report = discover_local(language)
        return {**report, "source": "container"}
    profile, source = selected_profile(language, root)
    return {**inspect_profile(language, profile), "source": source}


def error_boundary(function):
    from functools import wraps

    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ToolchainError, OSError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc

    return wrapped


@click.group()
def toolchain() -> None:
    """Inspect, prepare, and select language toolchains."""


@toolchain.command(name="list")
@click.option("--json", "as_json", is_flag=True)
@error_boundary
def list_toolchains(as_json: bool) -> None:
    emit_reports(
        [report_for(language, project_root()) for language in LANGUAGES], as_json
    )


@toolchain.command()
@click.argument("language", type=click.Choice(LANGUAGES))
@click.option("--json", "as_json", is_flag=True)
@error_boundary
def status(language: str, as_json: bool) -> None:
    report = report_for(language, project_root())
    if report["mode"] == "docker":
        report["local_alternatives"] = discover_local(language)["tools"]
    emit_reports([report], as_json)
    if not as_json and report.get("local_alternatives"):
        click.echo("  Local alternatives:")
        for row in report["local_alternatives"]:
            if row["location"]:
                click.echo(
                    f"    {row['tool']}: {row['location']} {row['version'] or '-'} ({row['status']})"
                )


@click.command()
@click.option("--lang", "language", type=click.Choice(LANGUAGES))
@click.option("--all", "all_languages", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
@error_boundary
def doctor(language: str | None, all_languages: bool, as_json: bool) -> None:
    if language and all_languages:
        raise click.UsageError("Use --lang or --all, not both.")
    reports = [
        report_for(item, project_root())
        for item in ([language] if language else LANGUAGES)
    ]
    emit_reports(reports, as_json)
    if not all(report["ready"] for report in reports):
        raise click.exceptions.Exit(1)


def prepare(
    languages: list[str],
    mode: str,
    *,
    image: str | None = None,
    install: bool = False,
    yes: bool = False,
    upgrade: bool = False,
) -> None:
    profiles = {}
    for language in languages:
        selected, _ = selected_profile(language, project_root(), mode=mode, image=image)
        profile = selected or {"mode": mode}
        if mode == "docker":
            profile.setdefault("image", default_image(language))
            profile.setdefault("platform", CATALOG["docker_platform"])
        validate_profile(language, profile)
        profiles[language] = profile
    if mode == "docker":
        commands = []
        for language in languages:
            profile = profiles[language]
            commands.append(
                ["docker", "pull", "--platform", profile["platform"], profile["image"]]
            )
        commands = [
            list(command)
            for command in dict.fromkeys(tuple(command) for command in commands)
        ]
        if install:
            available, detail = docker_available()
            if not available:
                raise ToolchainError(detail)
        for command in commands:
            click.echo(shlex.join(command))
        if install:
            confirm_install(yes)
            for command in commands:
                execute(list(command), os.environ.copy())
            reports = [
                inspect_profile(language, profiles[language]) for language in languages
            ]
            emit_reports(reports)
            if not all(report["ready"] for report in reports):
                raise ToolchainError(
                    "Some Docker toolchains are not ready; see the report above."
                )
        return
    if image:
        raise click.UsageError("--image requires --mode docker.")
    names = installation_plan(languages, upgrade=upgrade, profiles=profiles)
    for language in languages:
        for row in discover_local(language, profiles[language])["tools"]:
            if row["status"] == "ready" and row["tool"] not in names:
                click.echo(f"{row['tool']}: found {row['version']}; skipping")
    if not names:
        click.echo("All selected local toolchains are ready.")
        return
    prerequisites = prerequisite_commands(names)
    click.echo("System prerequisites (administrator-managed):")
    for command in prerequisites:
        click.echo(shlex.join(command))
    command = [
        sys.executable,
        "-m",
        "tarawasm.cli",
        "toolchain",
        "setup",
        *(["--all"] if len(languages) > 1 else languages),
        "--mode",
        mode,
        "--install",
        "--yes",
    ]
    if upgrade:
        command.append("--upgrade")
    click.echo(shlex.join(command))
    if install:
        # Preflight before creating managed directories or downloading anything.
        if "python3" in names:
            raise ToolchainError(
                "Install Python 3.10+ first; tarawasm does not replace system Python."
            )
        confirm_install(yes)
        for prerequisite in prerequisites:
            environment = os.environ.copy()
            if prerequisite[0] == "brew":
                environment.update(
                    HOMEBREW_NO_AUTO_UPDATE="1", HOMEBREW_NO_INSTALL_UPGRADE="1"
                )
            execute(prerequisite, environment)
        install_tools(names)
        reports = [
            discover_local(language, profiles[language]) for language in languages
        ]
        emit_reports(reports)
        if not all(report["ready"] for report in reports):
            raise ToolchainError(
                "Some local toolchains are not ready; see the report above."
            )


def confirm_install(yes: bool) -> None:
    if yes:
        return
    if not interactive():
        raise ToolchainError(
            "Installation requires --yes without an interactive terminal."
        )
    click.confirm("Execute this installation plan?", abort=True)


@toolchain.command()
@click.argument("language", required=False, type=click.Choice(LANGUAGES))
@click.option("--all", "all_languages", is_flag=True)
@click.option("--mode", type=click.Choice(["local", "docker"]))
@click.option("--image")
@click.option("--install", is_flag=True)
@click.option("--yes", is_flag=True)
@click.option("--upgrade", is_flag=True)
@error_boundary
def setup(
    language: str | None,
    all_languages: bool,
    mode: str | None,
    image: str | None,
    install: bool,
    yes: bool,
    upgrade: bool,
) -> None:
    if bool(language) == all_languages:
        raise click.UsageError("Choose one language or --all.")
    languages = list(LANGUAGES) if all_languages else [str(language)]
    if mode is None:
        profiles = [selected_profile(item, project_root())[0] for item in languages]
        modes = {profile["mode"] if profile else None for profile in profiles}
        if len(modes) == 1 and None not in modes:
            mode = modes.pop()
        elif interactive():
            mode = click.prompt(
                "Execution mode",
                type=click.Choice(["local", "docker"]),
                default="local",
            )
        else:
            raise click.UsageError("Specify --mode local or --mode docker.")
    assert mode is not None
    prepare(languages, mode, image=image, install=install, yes=yes, upgrade=upgrade)


@toolchain.command()
@click.argument("language", type=click.Choice(LANGUAGES))
@click.option("--mode", required=True, type=click.Choice(["local", "docker"]))
@click.option("--image")
@click.option(
    "--project", is_flag=True, help="Save for the current project instead of the user."
)
@error_boundary
def use(language: str, mode: str, image: str | None, project: bool) -> None:
    root = project_root() if project else None
    if project and root is None:
        raise ToolchainError("--project requires a tarawasm project.")
    if image and mode != "docker":
        raise click.UsageError("--image requires --mode docker.")
    profile, _ = selected_profile(language, root, mode=mode, image=image)
    profile = profile or {"mode": mode}
    if mode == "docker":
        profile.setdefault("image", default_image(language))
        profile.setdefault("platform", CATALOG["docker_platform"])
    validate_profile(language, profile)
    report = inspect_profile(language, profile)
    emit_reports([report])
    if not report["ready"]:
        raise ToolchainError(
            f"Selection unchanged. Prepare with: tarawasm toolchain setup {language} --mode {mode} --install"
        )
    save_profile(language, profile, root)
    click.echo(f"Selected {mode} toolchain for {language}.")


@toolchain.command(name="set")
@click.argument("language", type=click.Choice(LANGUAGES))
@click.argument("tool", type=click.Choice(list(TOOLS)))
@click.option(
    "--path",
    required=True,
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
)
@click.option("--project", is_flag=True)
@error_boundary
def set_tool(language: str, tool: str, path: Path, project: bool) -> None:
    if tool not in tools_for(language):
        raise click.UsageError(f"{tool} does not belong to {language}.")
    if TOOLS[tool]["kind"] == "npm-package":
        raise click.UsageError(
            "This is a package dependency, not an executable. Configure node/jco instead."
        )
    root = project_root() if project else None
    if project and root is None:
        raise ToolchainError("--project requires a tarawasm project.")
    current, _ = selected_profile(language, root)
    if current and current["mode"] == "docker":
        raise ToolchainError("Select a local toolchain before setting binary paths.")
    profile = dict(current or {"mode": "local"})
    profile["tools"] = {**profile.get("tools", {}), tool: str(path.resolve())}
    report = discover_local(language, profile)
    emit_reports([report])
    target = next(row for row in report["tools"] if row["tool"] == tool)
    if target["status"] != "ready":
        raise ToolchainError(
            "Selection unchanged: the replacement binary is not ready."
        )
    save_profile(language, profile, root)
    if not report["ready"]:
        click.echo(
            "Binary configured; the remaining tools must be prepared before building."
        )


@toolchain.command()
@click.argument("language", type=click.Choice(LANGUAGES))
@error_boundary
def lock(language: str) -> None:
    """Pin the checked versions and image digest for the current project."""
    root = project_root()
    if root is None:
        raise ToolchainError("Locking requires a tarawasm project.")
    profile, _ = selected_profile(language, root)
    profile = profile or {"mode": "local"}
    report = inspect_profile(language, profile)
    if not report["ready"]:
        raise ToolchainError("Only a ready toolchain can be locked.")
    entry = {
        "mode": profile["mode"],
        "versions": {row["tool"]: row["version"] for row in report["tools"]},
    }
    if profile["mode"] == "docker":
        digests = report.get("digests", [])
        if not digests:
            raise ToolchainError(
                "Image has no registry digest; publish/download it before locking."
            )
        entry.update(image=digests[0], platform=report["platform"])
    data = read_settings(root / LOCK_FILE)
    data["languages"][language] = entry
    write_settings(root / LOCK_FILE, data)
    click.echo(f"Locked {language} in {root / LOCK_FILE}.")

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path

import click

from tarawasm.config import Config, ConfigError

from .catalog import CATALOG, default_image
from .cli import emit_reports, interactive, prepare
from .discovery import (
    discover_local,
    docker_prefix,
    inspect_profile,
    local_execution_environment,
)
from .settings import (
    LOCK_FILE,
    ToolchainError,
    read_settings,
    save_profile,
    selected_profile,
    validate_profile,
)

ACTIVE: ContextVar[dict | None] = ContextVar("tarawasm_toolchain", default=None)


def executable(name: str) -> str:
    profile = ACTIVE.get()
    return profile.get("tools", {}).get(name, name) if profile else name


def command_argv(argv: tuple[str, ...]) -> tuple[str, ...]:
    # cargo dispatches subcommands by basename. Invoke an overridden plugin
    # directly so a differently named executable is actually honored.
    profile = ACTIVE.get() or {}
    component = profile.get("tools", {}).get("cargo-component")
    if component and argv[:2] == ("cargo", "component"):
        return (component, "component", *argv[2:])
    return (executable(argv[0]), *argv[1:])


def command_arguments(context: click.Context) -> list[str]:
    ancestors = []
    parent = context
    while parent.parent:
        ancestors.append(str(parent.info_name))
        parent = parent.parent
    argv = list(reversed(ancestors))
    trailing = []
    for parameter in context.command.params:
        value = context.params.get(str(parameter.name))
        if parameter.name in {"execution", "non_interactive"} or value is None:
            continue
        if isinstance(parameter, click.Option):
            if parameter.is_flag:
                if value:
                    argv.append(parameter.opts[0])
            else:
                argv.extend([parameter.opts[0], str(value)])
        elif parameter.name == "tool_args":
            trailing.extend(value)
        else:
            (
                argv.extend(str(item) for item in value)
                if isinstance(value, tuple)
                else argv.append(str(value))
            )
    if trailing:
        argv.extend(["--", *trailing])
    argv.extend(context.args)
    return argv


@contextmanager
def docker_user_file(language: str):
    if language != "js" or os.getuid() == 0:
        yield None
        return
    # componentize-js clears Wizer's environment, including HOME. Its native
    # runtime then resolves home through getpwuid. Supply only an operation-local
    # account description, without starting the image as root or exposing host NSS.
    with tempfile.TemporaryDirectory(prefix="tarawasm-docker-user-") as directory:
        path = Path(directory) / "passwd"
        path.write_text(
            "root:x:0:0:root:/root:/bin/sh\n"
            f"tarawasm-user:x:{os.getuid()}:{os.getgid()}:tarawasm:/tmp/tarawasm-home:/bin/sh\n"
        )
        yield path


def docker_command(
    profile: dict,
    language: str,
    context: click.Context,
    root: Path | None,
    *,
    identity: Path | None = None,
) -> list[str]:
    # Preserve absolute paths so persisted WIT/config paths remain portable back
    # to the host. Bind only the project, explicit inputs, and output parents.
    cwd = Path.cwd().resolve()
    if cwd == Path("/"):
        raise ToolchainError("Refusing to mount the host filesystem root.")
    mounts: dict[Path, bool] = {cwd: True}

    def add(path: Path, writable: bool) -> None:
        candidate = path.expanduser().resolve()
        while not candidate.exists():
            candidate = candidate.parent
        if writable and candidate.is_file():
            candidate = candidate.parent
        if candidate == Path("/"):
            raise ToolchainError("Refusing to mount the host filesystem root.")
        for mounted, write in list(mounts.items()):
            if candidate.is_relative_to(mounted) and (write or not writable):
                return
        mounts[candidate] = mounts.get(candidate, False) or writable

    if root:
        add(root, True)
    params = context.params
    for key in ("wit_path", "component", "source", "wasm"):
        if params.get(key):
            add(Path(params[key]), False)
    if params.get("project_dir"):
        add(Path(params["project_dir"]), True)
    if params.get("output"):
        add(Path(params["output"]), True)
    if root and (root / "tarawasm.json").exists():
        conf = Config.load(root)
        resolving = (
            context.parent is not None
            and context.parent.info_name == "deps"
            and context.info_name in {"resolve", "update"}
            and not params.get("dry_run", False)
        )
        add(conf.resolve_path(conf.wit_path), resolving)
        add(conf.resolve_path(conf.source), False)
        add(conf.resolve_path(conf.output), True)
    # strip forwards arbitrary output flags; make explicit destinations visible.
    extra = context.args
    if params.get("wasm") and not any(
        value in {"--output", "-o"} or value.startswith("--output=") for value in extra
    ):
        add(Path(str(params["wasm"]).rsplit(".", 1)[0] + ".strip.wasm"), True)
    for index, value in enumerate(extra):
        if value in {"--output", "-o"} and index + 1 < len(extra):
            add(Path(extra[index + 1]), True)
        elif value.startswith("--output="):
            add(Path(value.partition("=")[2]), True)
    argv = docker_prefix(profile)
    if os.getuid() != 0:
        argv.extend(["--user", f"{os.getuid()}:{os.getgid()}"])
    if identity is not None:
        if "," in str(identity) or "\n" in str(identity):
            raise ToolchainError("Docker bind paths cannot contain commas or newlines.")
        argv.extend(
            ["--mount", f"type=bind,source={identity},target=/etc/passwd,readonly"]
        )
    argv.extend(
        [
            "-e",
            "HOME=/tmp/tarawasm-home",
            "-e",
            "INSIDE_DOCKER=1",
            "-e",
            f"TARAWASM_TOOLCHAIN_LANGUAGE={language}",
            "-e",
            "TARAWASM_PY_SITE_PACKAGES="
            + str((root or cwd) / ".tarawasm/site-packages"),
        ]
    )
    for path, writable in sorted(mounts.items(), key=lambda item: len(item[0].parts)):
        rendered = str(path)
        if "," in rendered or "\n" in rendered:
            raise ToolchainError("Docker bind paths cannot contain commas or newlines.")
        mount = f"type=bind,source={rendered},target={rendered}"
        if not writable:
            mount += ",readonly"
        argv.extend(["--mount", mount])
    argv.extend(
        [
            "-w",
            str(cwd),
            profile.get("image", default_image(language)),
            *command_arguments(context),
        ]
    )
    return argv


def execution_options(function):
    """Keep a complete CLI operation in one local or container environment."""

    @wraps(function)
    def wrapped(*args, **kwargs):
        requested = kwargs.pop("execution", None)
        non_interactive = kwargs.pop("non_interactive", False)
        context = click.get_current_context()
        try:
            if ACTIVE.get() is not None:
                return function(*args, **kwargs)
            language = kwargs.get("language")
            root = (
                Path(kwargs.get("project_dir", ".")).expanduser().resolve()
                if language
                else None
            )
            if language is None:
                try:
                    conf = Config.load()
                    root, language = conf.project_root, conf.language
                except ConfigError:
                    if context.info_name == "strip":
                        language = "python"
                    else:
                        return function(*args, **kwargs)
            if os.environ.get("INSIDE_DOCKER") == "1":
                container_language = os.environ.get(
                    "TARAWASM_TOOLCHAIN_LANGUAGE", "all"
                )
                if requested == "docker":
                    raise ToolchainError(
                        "Already inside Docker; nested Docker execution is not supported."
                    )
                if container_language not in {"all", language, "base"}:
                    raise ToolchainError(
                        f"Container provides {container_language}, not {language}."
                    )
                if root:
                    locked = read_settings(root / LOCK_FILE)["languages"].get(language)
                    if locked and not kwargs.get("dry_run", False):
                        report = discover_local(
                            language,
                            {"mode": "local", "versions": locked.get("versions", {})},
                        )
                        if not report["ready"]:
                            emit_reports([report])
                            raise ToolchainError(
                                "Container tools differ from the project lock."
                            )
                return function(*args, **kwargs)
            profile, source = selected_profile(language, root, mode=requested)
            if requested == "docker":
                profile.setdefault("image", default_image(language))
                profile.setdefault("platform", CATALOG["docker_platform"])
            onboarding = context.info_name in {"init", "import"}
            dry_run = kwargs.get("dry_run", False)
            remember = profile is None and onboarding and not dry_run
            if profile is None:
                profile = {"mode": "local"}
                if remember:
                    report = discover_local(language)
                    emit_reports([report])
                    if not report["ready"]:
                        if non_interactive or not interactive():
                            raise ToolchainError(
                                f"Toolchain is incomplete. Run tarawasm toolchain setup {language} --mode local --install --yes, or select --execution docker."
                            )
                        mode = click.prompt(
                            "Execution mode",
                            type=click.Choice(["local", "docker"]),
                            default="docker",
                        )
                        profile = {"mode": mode}
                        if mode == "docker":
                            profile["image"] = default_image(language)
                        if click.confirm(
                            "Prepare this toolchain automatically?", default=False
                        ):
                            prepare([language], mode, install=True, yes=True)
                        else:
                            prepare([language], mode)
                            raise ToolchainError(
                                "Run the preparation commands, then repeat init/import."
                            )
                    click.echo(
                        f"Using {profile['mode']} {language} toolchain. To change: tarawasm toolchain use {language} --mode {'docker' if profile['mode'] == 'local' else 'local'}"
                    )
            validate_profile(language, profile)
            # Explicit/saved environments are checked without silently falling
            # back. Legacy unconfigured build still executes existing commands.
            if (requested or source != "discovery" or remember) and not dry_run:
                report = inspect_profile(language, profile)
                if not report["ready"]:
                    emit_reports([report])
                    raise ToolchainError(
                        f"Selected toolchain is not ready. Run tarawasm toolchain setup {language} --mode {profile['mode']} --install."
                    )
            if profile["mode"] == "docker":
                with docker_user_file(language) as identity:
                    argv = docker_command(
                        profile, language, context, root, identity=identity
                    )
                    click.echo(f"Running: {shlex.join(argv)}")
                    subprocess.run(argv, check=True)
                if remember:
                    save_profile(language, profile, root)
                return None
            previous = os.environ.copy()
            token = ACTIVE.set(profile)
            try:
                with local_execution_environment(profile) as environment:
                    os.environ.update(environment)
                    result = function(*args, **kwargs)
                if remember:
                    save_profile(language, profile, root)
                return result
            finally:
                ACTIVE.reset(token)
                os.environ.clear()
                os.environ.update(previous)
        except (ToolchainError, OSError, subprocess.CalledProcessError) as exc:
            raise click.ClickException(str(exc)) from exc

    wrapped = click.option(
        "--execution",
        type=click.Choice(["local", "docker"]),
        help="Override the selected execution environment.",
    )(wrapped)
    return click.option(
        "--non-interactive", is_flag=True, help="Never prompt for toolchain setup."
    )(wrapped)

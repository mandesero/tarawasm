from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import click

from tarawasm.config import (
    LANG_CFGS,
    Config,
    ConfigError,
    copy_runtime_wasm,
    load_template,
)
from tarawasm.languages import bind_args, build_args


def _validate_common_options_not_in_tool_args(
    tool_args: list[str], common_options: set[str]
) -> None:
    for token in tool_args:
        if not token.startswith("-"):
            continue
        option = token.split("=", 1)[0]
        if option in common_options:
            raise click.ClickException(
                f"Common option '{option}' must be provided before '--'."
            )


def _make_all_writable(path: str = "."):
    if os.getenv("INSIDE_DOCKER") != "1":
        return

    for root, dirs, files in os.walk(path):

        for name in files:
            file_path = os.path.join(root, name)

            if os.path.islink(file_path) and not os.path.exists(file_path):
                continue

            os.chmod(
                file_path,
                stat.S_IRUSR
                | stat.S_IWUSR
                | stat.S_IRGRP
                | stat.S_IWGRP
                | stat.S_IROTH
                | stat.S_IWOTH,
            )

        for name in dirs:
            dir_path = os.path.join(root, name)
            os.chmod(
                dir_path,
                stat.S_IRUSR
                | stat.S_IWUSR
                | stat.S_IXUSR
                | stat.S_IRGRP
                | stat.S_IWGRP
                | stat.S_IXGRP
                | stat.S_IROTH
                | stat.S_IWOTH
                | stat.S_IXOTH,
            )


@click.group()
def cli() -> None:
    """tarawasm: CLI for building WebAssembly components"""
    pass


@cli.command()
@click.argument("world")
@click.option(
    "--lang",
    "-l",
    required=True,
    type=click.Choice(list(LANG_CFGS.keys())),
    help="Guest language to use",
)
@click.option(
    "--wasm-file", "-w", required=True, help="Path to the .wasm file for init step"
)
@click.option(
    "--wit-dir",
    default="./wit",
    help="Directory to write WIT definitions (default: ./wit)",
)
@click.option(
    "--src-file",
    "-s",
    default=None,
    help="Source file to compile (default per language)",
)
def init(
    world: str,
    lang: str,
    wasm_file: str,
    wit_dir: str,
    src_file: str | None,
) -> None:
    """Initialize project and save configuration"""
    # Validate language
    cfg = LANG_CFGS[lang]
    default_src = cfg.get("default-src")
    src = src_file or default_src
    if src is None:
        raise click.ClickException("No source file specified and no default available")
    # Extract WIT if needed
    wasm_path = Path(wasm_file)
    if not wasm_path.exists():
        raise click.ClickException(f"WASM file '{wasm_file}' not found")

    if lang == "rust":
        subprocess.run(["cargo", "component", "new", "--lib", world], check=True)
        src_dir = Path(world)
        for item in src_dir.iterdir():
            target = Path(".") / item.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            shutil.move(str(item), str(target))
        src_dir.rmdir()
        wit_output = Path("./wit")
        out_wit = wit_output / "world.wit"
    else:
        wit_output = Path(wit_dir)
        wit_output.mkdir(parents=True, exist_ok=True)
        out_wit = wit_output / f"{world}.wit"

    if lang == "c":
        copy_runtime_wasm()

    if lang == "go":
        if not Path("go.mod").exists():
            click.echo("Initializing Go module...")
            subprocess.run(["go", "mod", "init", f"{world}-wasm-bindings"], check=True)
            subprocess.run(
                [
                    "go",
                    "get",
                    "-tool",
                    "go.bytecodealliance.org/cmd/wit-bindgen-go@v0.7.0",
                ],
                check=True,
            )
            subprocess.run(["go", "get", "go.bytecodealliance.org@v0.7.0"], check=True)

    click.echo(f"Extracting WIT from '{wasm_file}' to '{out_wit}'...")
    with open(out_wit, "w") as f:
        subprocess.run(
            ["wasm-tools", "component", "wit", str(wasm_path)], check=True, stdout=f
        )

    tpl = load_template(lang)
    content = tpl.replace("${world}", world)

    out = Path(src)
    if not out.exists() or lang == "rust":
        out.write_text(content)

    # Save config
    conf = Config(world, lang, wit_output, src, wasm_file)
    conf.save()
    _make_all_writable()
    click.echo("Configuration saved to 'tarawasm.json'")


@cli.command()
@click.pass_context
def clean(ctx: click.Context) -> None:
    """Remove build artifacts"""
    try:
        conf = Config.load()
    except ConfigError as e:
        raise click.ClickException(str(e))

    lang = conf.lang
    world = conf.world
    wasm_file = conf.wasm_file

    click.echo(f"Cleaning {lang} artifacts for world '{world}'...")
    if lang == "python":
        shutil.rmtree("wit_world", ignore_errors=True)
        click.echo("Removed directory 'wit_world'")
    elif lang == "go" or lang == "js":
        for item in Path(".").glob("internal"):
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink()
        click.echo(f"Cleaned {lang} artifacts")
    elif lang == "rust":
        target_dir = Path("target")
        if target_dir.exists() and target_dir.is_dir():
            shutil.rmtree(target_dir)
    else:
        click.echo(f"Clean not implemented for {lang}")
        return

    input_wasm_name = Path(wasm_file).name
    for item in Path(".").glob("*.wasm"):
        if item.name != input_wasm_name:
            item.unlink()


@cli.command()
@click.option(
    "--world",
    default=None,
    help="Override world name from tarawasm.json for this run",
)
@click.option(
    "--wit",
    "wit_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Override WIT path from tarawasm.json for this run",
)
@click.option(
    "--tool-help",
    is_flag=True,
    help="Show help from the language-specific binding tool and exit",
)
@click.argument("tool_args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def bind(
    ctx: click.Context,
    world: str | None,
    wit_path: Path | None,
    tool_help: bool,
    tool_args: tuple[str, ...],
) -> None:
    """Generate bindings from WIT.

    Language-specific options can be passed after '--'.
    """
    _validate_common_options_not_in_tool_args(
        list(tool_args),
        {"--world", "--wit", "--tool-help"},
    )

    try:
        conf = Config.load()
    except ConfigError as e:
        raise click.ClickException(str(e))

    lang = conf.lang
    base_cmd, base_args = bind_args(
        lang,
        conf,
        world_override=world,
        wit_override=wit_path,
        tool_args=list(tool_args),
    )

    if tool_help:
        subprocess.run(base_cmd + ["--help"], check=False)
        return

    full_cmd = base_cmd + base_args
    click.echo(f"Running: {' '.join(full_cmd)}")
    subprocess.run(full_cmd, check=True)
    _make_all_writable()


@cli.command()
@click.option(
    "--world",
    default=None,
    help="Override world name from tarawasm.json for this run",
)
@click.option(
    "--src",
    "src_file",
    default=None,
    help="Override source file from tarawasm.json for this run",
)
@click.option(
    "--wit",
    "wit_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Override WIT path from tarawasm.json for this run",
)
@click.option(
    "--out",
    "out_file",
    default=None,
    help="Output WASM file (for C this is the final component output)",
)
@click.option(
    "--clean",
    "run_clean",
    is_flag=True,
    help="Run clean before build",
)
@click.option(
    "--tool-help",
    is_flag=True,
    help="Show help from the language-specific build tool and exit",
)
@click.argument("tool_args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def build(
    ctx: click.Context,
    world: str | None,
    src_file: str | None,
    wit_path: Path | None,
    out_file: str | None,
    run_clean: bool,
    tool_help: bool,
    tool_args: tuple[str, ...],
) -> None:
    """Compile source to wasm component.

    Language-specific options can be passed after '--'.
    """
    _validate_common_options_not_in_tool_args(
        list(tool_args),
        {"--world", "--src", "--wit", "--out", "--clean", "--tool-help"},
    )

    try:
        conf = Config.load()
    except ConfigError as e:
        raise click.ClickException(str(e))

    lang = conf.lang
    resolved_world = world or conf.world
    resolved_out = out_file or (
        f"{resolved_world}.component.wasm" if lang == "c" else f"{resolved_world}.wasm"
    )

    if lang not in LANG_CFGS:
        raise click.ClickException(f"Unsupported lang: {lang}")

    base_cmd, base_args = build_args(
        lang,
        conf,
        world_override=resolved_world,
        wit_override=wit_path,
        src_override=src_file,
        out_override=resolved_out,
        tool_args=list(tool_args),
    )

    if tool_help:
        subprocess.run(base_cmd + ["--help"], check=False)
        return

    if run_clean:
        ctx.invoke(clean)

    full_cmd = base_cmd + base_args
    click.echo(f"Running: {' '.join(full_cmd)}")
    run_env = os.environ.copy()
    if lang == "go" and "GOTOOLCHAIN" not in run_env:
        try:
            go_version = subprocess.check_output(["go", "version"], text=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            go_version = ""
        match = re.search(r"\bgo1\.(\d+)", go_version)
        if match and int(match.group(1)) >= 26:
            # TinyGo 0.40.x requires the Go 1.25 toolchain for guest builds.
            run_env["GOTOOLCHAIN"] = "go1.25.4+auto"
            click.echo("Detected Go 1.26+, using GOTOOLCHAIN=go1.25.4+auto for TinyGo.")

    subprocess.run(full_cmd, check=True, env=run_env)

    if lang == "rust":
        src_path = Path("target/wasm32-wasip1/release") / f"{resolved_world}.wasm"
        dst = Path(".") / resolved_out
        if src_path.exists():
            shutil.move(str(src_path), str(dst))
            click.echo(f"Moved {src_path} to {dst}")
        else:
            raise click.ClickException(f"WASM file '{src_path}' not found")

    if lang == "c":
        full_cmd = [
            "wasm-tools",
            "component",
            "new",
            f"{resolved_world}.wasm",
            "--adapt",
            "wasi_snapshot_preview1.wasm",
            "-o",
            resolved_out,
        ]
        click.echo(f"Running: {' '.join(full_cmd)}")
        subprocess.run(full_cmd, check=True)

    _make_all_writable()


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

    cmd = ["wasm-tools", "strip", wasm] + default_output + ctx.args
    click.echo(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


@cli.command()
@click.pass_context
def all(ctx: click.Context) -> None:
    """Run clean, bind, build, pack"""
    ctx.invoke(clean)
    ctx.invoke(bind)
    ctx.invoke(build)
    conf = Config.load()
    click.echo(f"{conf.world}.wasm is ready")


if __name__ == "__main__":
    cli()

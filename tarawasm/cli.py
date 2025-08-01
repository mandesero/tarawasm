from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Dict

import click

from tarawasm.config import (
    LANG_CFGS,
    Config,
    ConfigError,
    copy_runtime_wasm,
    load_template,
)
from tarawasm.languages import bind_args, build_args


def _parse_extra_args(args: list[str]) -> Dict[str, str | None]:
    extras: Dict[str, str | None] = {}
    for arg in args:
        if "=" in arg:
            key, val = arg.split("=", 1)
            extras[key] = val
        else:
            extras[arg] = None
    return extras


def _merge_args(base_args: list[str], user_args: Dict[str, str | None]) -> list[str]:
    final: list[str] = []
    for arg in base_args:
        if "=" in arg:
            key, val = arg.split("=", 1)
            if key in user_args:
                new_val = user_args.pop(key)
                final.append(f"{key}={new_val}")
            else:
                final.append(arg)
        elif arg in user_args:
            user_args.pop(arg)
            final.append(arg)
        else:
            final.append(arg)

    for key, val_ in user_args.items():
        if val_ is None:
            final.append(key)
        else:
            final.append(f"{key}={val_}")
    return final


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
                ["go", "get", "go.bytecodealliance.org/cmd/wit-bindgen-go"], check=True
            )
            subprocess.run(["go", "get", "go.bytecodealliance.org/cm"], check=True)

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

    for item in Path(".").glob("*.wasm"):
        if item != wasm_file:
            item.unlink()


@cli.command(
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
    add_help_option=False,
)
@click.pass_context
def bind(ctx: click.Context) -> None:
    """Generate bindings from WIT."""
    try:
        conf = Config.load()
    except ConfigError as e:
        raise click.ClickException(str(e))

    lang = conf.lang
    base_cmd, base_args = bind_args(lang, conf)

    if "--help" in ctx.args or "-h" in ctx.args:
        subprocess.run(base_cmd + ["--help"], check=False)
        return

    user_args = _parse_extra_args(ctx.args)
    final_args = _merge_args(base_args, user_args)

    full_cmd = base_cmd + final_args
    click.echo(f"Running: {' '.join(full_cmd)}")
    subprocess.run(full_cmd, check=True)
    _make_all_writable()


@cli.command(
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
    add_help_option=False,
)
@click.pass_context
def build(ctx: click.Context) -> None:
    """Compile source to wasm component."""
    try:
        conf = Config.load()
    except ConfigError as e:
        raise click.ClickException(str(e))

    lang = conf.lang
    world = conf.world

    base_cmd, base_args = build_args(lang, conf)

    if lang not in LANG_CFGS:
        raise click.ClickException(f"Unsupported lang: {lang}")

    if "--help" in ctx.args or "-h" in ctx.args:
        subprocess.run(base_cmd + ["--help"], check=False)
        return

    user_args = _parse_extra_args(ctx.args)
    final_args = _merge_args(base_args, user_args)

    full_cmd = base_cmd + final_args
    click.echo(f"Running: {' '.join(full_cmd)}")
    subprocess.run(full_cmd, check=True)

    if lang == "rust":
        src_path = Path("target/wasm32-wasip1/release") / f"{world}.wasm"
        dst = Path(".") / f"{world}.wasm"
        if src_path.exists():
            shutil.move(str(src_path), str(dst))
            click.echo(f"Moved {src_path} to {dst}")
        else:
            raise click.ClickException(f"WASM file '{src_path}' not found")

    if lang == "c":
        full_cmd = f"wasm-tools component new {world}.wasm --adapt wasi_snapshot_preview1.wasm -o {world}.component.wasm".split()
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

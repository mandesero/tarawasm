import subprocess
import shutil
from pathlib import Path
import json
import click

# Configuration file path
CONFIG_FILE = 'tarawasm.json'

# Supported languages and defaults
LANG_CFGS = {
    'python': {
        'wit-flag': '--wit-path',
        'default-src': 'main.py'
    },
    'go': {
        'wit-flag': '--wit-dir',
        # Ensure installed via: go install go.bytecodealliance.org/cmd/wit-bindgen-go@latest
        'bindgen-cmd': 'wit-bindgen-go',
        'tinygo-target': 'wasip2',
        'default-src': 'main.go'
    },
    'js': {
        'wit-flag': '--wit',
        'default-src': 'main.js'
    },
    'rust': {
        'default-src': 'src/lib.rs',
        'cargo-component': 'cargo',
        'release-target': 'wasm32-wasip1'
  }
}

TEMPLATES = {
    'python': '''from {world} import exports

class Run(exports.Run):
    def run(self) -> None:
        print("Hello from Python WASM!")''',

    'go': '''package main

import (
    "fmt"
    "{world}-wasm-bindings/internal/wasi/cli/run"
    "go.bytecodealliance.org/cm"
)

func init() {
    run.Exports.Run = func() (result cm.BoolResult) {
        fmt.Println("Hello from Go WASM!")
        return cm.BoolResult(true)
    }
}

func main() {{}}''',

    'js': '''export const run = {
    run: async function() {
        console.info("Hello from JS WASM!")
    }
}   ''',

    'rust': '''#[allow(warnings)]
mod bindings;

use bindings::exports::wasi::cli::run::Guest;

struct Component;

impl Guest for Component {{
    fn run() -> Result<(),()> {{
        println!("Hello from Rust WASM!");
        Ok(())
    }}
}}

bindings::export!(Component with_types_in bindings);'''
}


class ConfigError(Exception):
    pass

def load_config():
    if not Path(CONFIG_FILE).exists():
        raise ConfigError(f"Config file '{CONFIG_FILE}' not found. Run 'init' first.")
    return json.loads(Path(CONFIG_FILE).read_text())

@click.group()
def cli():
    """wasmcraft: CLI for building WebAssembly components"""
    pass

@cli.command()
@click.argument('world')
@click.option('--lang', '-l', required=True, type=click.Choice(list(LANG_CFGS.keys())), help='Guest language to use')
@click.option('--wasm-file', '-w', required=True, help='Path to the .wasm file for init step')
@click.option('--wit-dir', default='./wit', help='Directory to write WIT definitions (default: ./wit)')
@click.option('--src-file', '-s', default=None, help='Source file to compile (default per language)')
def init(world, lang, wasm_file, wit_dir, src_file):
    """Initialize project and save configuration"""
    # Validate language
    cfg = LANG_CFGS[lang]
    # Determine src file
    default_src = cfg.get('default-src')
    src = src_file or default_src
    # Extract WIT if needed
    wasm_path = Path(wasm_file)
    if not wasm_path.exists():
        raise click.ClickException(f"WASM file '{wasm_file}' not found")

    if lang == 'rust':
        subprocess.run(['cargo', 'component', 'new', '--lib', world], check=True)
        src_dir = Path(world)
        for item in src_dir.iterdir():
            target = Path('.') / item.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            shutil.move(str(item), str(target))
        src_dir.rmdir()
        wit_output = Path('./wit')
        out_wit = wit_output / f"world.wit"
    else:
        wit_output = Path(wit_dir)
        wit_output.mkdir(parents=True, exist_ok=True)
        out_wit = wit_output / f"{world}.wit"

    click.echo(f"Extracting WIT from '{wasm_file}' to '{out_wit}'...")    
    with open(out_wit, 'w') as f:
        subprocess.run(['wasm-tools', 'component', 'wit', str(wasm_path)], check=True, stdout=f)

    template = TEMPLATES.get(lang)
    if src and template:
        src_path = Path(src)
        with open(src_path, 'w') as f:
            rendered = template.format(world=world)
            print(rendered, file=f)
            click.echo(f"Created starter source file: {src}")

    # Save config
    conf = {
        'world': world,
        'lang': lang,
        'wit_path': str(wit_output),
        'src_file': src,
        'wasm_file': wasm_file,
    }
    Path(CONFIG_FILE).write_text(json.dumps(conf, indent=2))
    click.echo(f"Configuration saved to '{CONFIG_FILE}'")

@cli.command()
@click.pass_context
def clean(ctx):
    """Remove old build artifacts"""
    try:
        conf = load_config()
    except ConfigError as e:
        raise click.ClickException(str(e))
    lang = conf['lang']
    world = conf['world']
    click.echo(f"Cleaning {lang} artifacts for world '{world}'...")
    if lang == 'python':
        shutil.rmtree(world, ignore_errors=True)
        click.echo(f"Removed directory '{world}'")
    elif lang == 'go' or lang == 'js':
        for pattern in ('*.wasm', 'internal'):
            for item in Path('.').glob(pattern):
                if item.is_dir(): shutil.rmtree(item, ignore_errors=True)
                else: item.unlink()
        click.echo("Cleaned Go artifacts")
    elif lang == 'rust':
        target_dir = Path("target")
        if target_dir.exists() and target_dir.is_dir():
            shutil.rmtree(target_dir)
    else:
        click.echo(f"Clean not implemented for {lang}")

@cli.command()
@click.pass_context
def bind(ctx):
    """Generate bindings from WIT"""
    try:
        conf = load_config()
    except ConfigError as e:
        raise click.ClickException(str(e))
    lang = conf['lang']
    world = conf['world']
    wit_path = conf['wit_path']
    cfg = LANG_CFGS[lang]
    click.echo(f"Generating {lang} bindings for world '{world}' with WIT path '{wit_path}'...")
    if lang == 'python':
        subprocess.run([
            'componentize-py',
            f"{cfg['wit-flag']}={wit_path}",
            f"--world={world}",
            'bindings',
            '.'
        ], check=True)
    elif lang == 'go':
        # Ensure Go module
        if not Path('go.mod').exists():
            click.echo("Initializing Go module for WIT bindings...")
            subprocess.run(['go', 'mod', 'init', f"{world}-wasm-bindings"], check=True)
            subprocess.run(['go', 'get', 'go.bytecodealliance.org/cmd/wit-bindgen-go'], check=True)
            subprocess.run(['go', 'get', 'go.bytecodealliance.org/cm'], check=True)
        subprocess.run([
            cfg['bindgen-cmd'], 'generate',
            '-o', 'internal/', wit_path
        ], check=True)
        click.echo("Go bindings generated")
    elif lang == 'js':
        subprocess.run([
            'jco', 'guest-types',
            '-o', 'internal',
            wit_path
        ], check=True)
        click.echo("JS guest types generated")
    elif lang == 'rust':
        subprocess.run(['cargo', 'component', 'bindings'], check=True)
        click.echo("Rust guest types generated")
    else:
        click.echo(f"Bind not implemented for {lang}")

@cli.command()
@click.pass_context
def build(ctx):
    """Compile source to wasm component"""
    try:
        conf = load_config()
    except ConfigError as e:
        raise click.ClickException(str(e))
    lang = conf['lang']
    world = conf['world']
    src = conf['src_file']
    wit_path = conf['wit_path']
    wasm_file = conf['wasm_file']
    cfg = LANG_CFGS[lang]
    click.echo(f"Building {lang} component for world '{world}' from '{src}' with WIT path '{wit_path}'...")
    if lang == 'python':
        subprocess.run([
            'componentize-py',
            f"{cfg['wit-flag']}={wit_path}",
            f"--world={world}",
            'componentize',
            src.split('.')[0],
            '-o', f"{world}.wasm"
        ], check=True)
    elif lang == 'go':
        subprocess.run([
            'tinygo', 'build',
            f"-target={cfg['tinygo-target']}",
            '-o', f"{world}.wasm",
            '--wit-package', wasm_file,
            '--wit-world', world,
            src
        ], check=True)
        click.echo("Go component built")
    elif lang == 'js':
        subprocess.run([
            'jco', 'componentize',
            src,
            cfg['wit-flag'], wit_path,
            '--world-name', world,
            '--out', f"{world}.wasm",
            '--disable', 'http'
        ], check=True)
        click.echo("JS component built")
    elif lang == 'rust':
        subprocess.run(['cargo', 'component', 'build', '--release'], check=True)
        src = Path("target/wasm32-wasip1/release") / f"{world}.wasm"
        dst = Path(".")
        if src.exists():
            shutil.move(str(src), str(dst))
        else:
            raise click.ClickException(f"WASM file '{src}' not found")
    else:
        click.echo(f"Build not implemented for {lang}")


@cli.command()
@click.pass_context
def all(ctx):
    """Run clean, bind, build, pack"""
    ctx.invoke(clean)
    ctx.invoke(bind)
    ctx.invoke(build)
    conf = load_config()
    click.echo(f"✅ {conf['world']}.wasm is ready")


if __name__ == '__main__':
    cli()

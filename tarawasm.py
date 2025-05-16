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
    }
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
    wit_output = Path(wit_dir)
    wit_output.mkdir(parents=True, exist_ok=True)
    out_wit = wit_output / f"{world}.wit"
    click.echo(f"Extracting WIT from '{wasm_file}' to '{out_wit}'...")
    with open(out_wit, 'w') as f:
        subprocess.run(['wasm-tools', 'component', 'wit', str(wasm_path)], check=True, stdout=f)
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

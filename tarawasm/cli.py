import subprocess
import shutil
from pathlib import Path
import json
import click
from importlib.resources import read_text

def load_template(lang: str) -> str:
    return read_text("tarawasm.templates", f"{lang}.tpl")

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

class ConfigError(Exception):
    pass

def load_config():
    if not Path(CONFIG_FILE).exists():
        raise ConfigError(f"Config file '{CONFIG_FILE}' not found. Run 'init' first.")
    return json.loads(Path(CONFIG_FILE).read_text())

@click.group()
def cli():
    """tarawasm: CLI for building WebAssembly components"""
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

    tpl = load_template(lang)
    content = tpl.replace("${world}", world)

    out = Path(src_file or default_src)
    out.write_text(content)

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
    """Remove build artifacts"""
    try:
        conf = load_config()
    except ConfigError as e:
        raise click.ClickException(str(e))

    lang = conf['lang']
    world = conf['world']
    wasm_file = conf['wasm_file']

    click.echo(f"Cleaning {lang} artifacts for world '{world}'...")
    if lang == 'python':
        shutil.rmtree("wit_world", ignore_errors=True)
        click.echo(f"Removed directory 'wit_world'")
    elif lang == 'go' or lang == 'js':
        for item in Path('.').glob('internal'):
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink()
        click.echo(f"Cleaned {lang} artifacts")
    elif lang == 'rust':
        target_dir = Path("target")
        if target_dir.exists() and target_dir.is_dir():
            shutil.rmtree(target_dir)
    else:
        click.echo(f"Clean not implemented for {lang}")
        return
    
    for item in Path('.').glob('*.wasm'):
        if item != wasm_file:
            item.unlink()


@cli.command(context_settings=dict(ignore_unknown_options=True, allow_extra_args=True), add_help_option=False)
@click.pass_context
def bind(ctx):
    """Generate bindings from WIT."""
    try:
        conf = load_config()
    except ConfigError as e:
        raise click.ClickException(str(e))

    lang = conf['lang']
    world = conf['world']
    wit_path = conf['wit_path']
    cfg = LANG_CFGS[lang]

    if lang == 'python':
        base_cmd = ['componentize-py']
        base_args = [f"{cfg['wit-flag']}={wit_path}", f"--world={world}", 'bindings', '.']
    elif lang == 'go':
        base_cmd = ['go', 'run', 'go.bytecodealliance.org/cmd/wit-bindgen-go', 'generate']
        base_args = ['-o', 'internal/', wit_path]
    elif lang == 'js':
        base_cmd = ['jco', 'guest-types']
        base_args = ['-o', 'internal', wit_path]
    elif lang == 'rust':
        base_cmd = ['cargo', 'component', 'bindings']
        base_args = []
    else:
        raise click.ClickException(f"Unsupported lang: {lang}")

    if '--help' in ctx.args or '-hc' in ctx.args:
        subprocess.run(base_cmd + ['--help'], check=False)
        return
    
    if lang == 'go':
        if not Path('go.mod').exists():
            click.echo("Initializing Go module...")
            subprocess.run(['go', 'mod', 'init', f"{world}-wasm-bindings"], check=True)
            subprocess.run(['go', 'get', 'go.bytecodealliance.org/cmd/wit-bindgen-go'], check=True)
            subprocess.run(['go', 'get', 'go.bytecodealliance.org/cm'], check=True)

    user_args = {}
    for arg in ctx.args:
        if '=' in arg:
            key, val = arg.split('=', 1)
            user_args[key] = val
        else:
            user_args[arg] = None

    final_args = []
    for arg in base_args:
        if '=' in arg:
            key, val = arg.split('=', 1)
            if key in user_args:
                new_val = user_args.pop(key)
                final_args.append(f"{key}={new_val}")
            else:
                final_args.append(arg)
        elif arg in user_args:
            user_args.pop(arg)
            final_args.append(arg)
        else:
            final_args.append(arg)

    for key, val in user_args.items():
        if val is None:
            final_args.append(key)
        else:
            final_args.append(f"{key}={val}")

    full_cmd = base_cmd + final_args
    click.echo(f"Running: {' '.join(full_cmd)}")
    subprocess.run(full_cmd, check=True)


@cli.command(context_settings=dict(ignore_unknown_options=True, allow_extra_args=True), add_help_option=False)
@click.pass_context
def build(ctx):
    """Compile source to wasm component."""
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

    if lang == 'python':
        base_cmd = ['componentize-py']
        base_args = [f"{cfg['wit-flag']}={wit_path}", f"--world={world}", 'componentize', src.split('.')[0], '-o', f"{world}.wasm"]
    elif lang == 'go':
        base_cmd = ['tinygo', 'build']
        base_args = [f"-target={cfg['tinygo-target']}", '-o', f"{world}.wasm", '--wit-package', wasm_file, '--wit-world', world, src]
    elif lang == 'js':
        base_cmd = ['jco', 'componentize']
        base_args = [src, cfg['wit-flag'], wit_path, '--world-name', world, '--out', f"{world}.wasm", '--disable', 'http']
    elif lang == 'rust':
        base_cmd = ['cargo', 'component', 'build']
        base_args = ['--release']
    else:
        raise click.ClickException(f"Unsupported lang: {lang}")

    if '--help' in ctx.args or '-h' in ctx.args:
        subprocess.run(base_cmd + ['--help'], check=False)
        return

    user_args = {}
    for arg in ctx.args:
        if '=' in arg:
            key, val = arg.split('=', 1)
            user_args[key] = val
        else:
            user_args[arg] = None

    final_args = []
    for arg in base_args:
        if '=' in arg:
            key, val = arg.split('=', 1)
            if key in user_args:
                new_val = user_args.pop(key)
                final_args.append(f"{key}={new_val}")
            else:
                final_args.append(arg)
        elif arg in user_args:
            user_args.pop(arg)
            final_args.append(arg)
        else:
            final_args.append(arg)

    for key, val in user_args.items():
        if val is None:
            final_args.append(key)
        else:
            final_args.append(f"{key}={val}")

    full_cmd = base_cmd + final_args
    click.echo(f"Running: {' '.join(full_cmd)}")
    subprocess.run(full_cmd, check=True)

    if lang == 'rust':
        src_path = Path("target/wasm32-wasip1/release") / f"{world}.wasm"
        dst = Path(".") / f"{world}.wasm"
        if src_path.exists():
            shutil.move(str(src_path), str(dst))
            click.echo(f"Moved {src_path} to {dst}")
        else:
            raise click.ClickException(f"WASM file '{src_path}' not found")


@cli.command()
@click.pass_context
def all(ctx):
    """Run clean, bind, build, pack"""
    ctx.invoke(clean)
    ctx.invoke(bind)
    ctx.invoke(build)
    conf = load_config()
    click.echo(f"{conf['world']}.wasm is ready")


if __name__ == '__main__':
    cli()

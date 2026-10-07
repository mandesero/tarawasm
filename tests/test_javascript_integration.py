"""Real npm archives, Jco compilation and execution of WIT exports."""

import json
import os
import shutil

import pytest
from utils import CLI_MODES, cli_mode_available, run_cli, run_tool

WIT = """package test:npm-sdk@0.1.0;
interface number-api {
    resource number-box {
        constructor(initial-value: u32);
        get-number: func() -> u32;
        from-number: static func(initial-value: u32) -> number-box;
    }
    add-number: func(first-number: u32, second-number: u32) -> u32;
}
world sdk {
    export add-number: func(first-number: u32, second-number: u32) -> u32;
    export number-api;
}
"""

# Resolve the shim from the actual Jco executable, including language images
# whose global compiler packages live outside npm's default global prefix.
RUNNER = """import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { existsSync, realpathSync, readFileSync, mkdirSync, symlinkSync } from 'node:fs';
import { delimiter, join, dirname } from 'node:path';
const jco = process.env.PATH.split(delimiter).map(p => join(p, 'jco')).find(existsSync);
const require = createRequire(realpathSync(jco));
let shim = dirname(require.resolve('@bytecodealliance/preview2-shim/cli'));
while (!existsSync(join(shim, 'package.json')) || JSON.parse(readFileSync(join(shim, 'package.json'), 'utf8')).name !== '@bytecodealliance/preview2-shim') {
    shim = dirname(shim);
}
mkdirSync('node_modules/@bytecodealliance', { recursive: true });
symlinkSync(shim, 'node_modules/@bytecodealliance/preview2-shim', 'dir');
const component = await import('./transpiled/sdk.js');
assert.equal(component.addNumber(19, 23), 42);
assert.equal(component.numberApi.addNumber(20, 22), 42);
assert.equal(new component.numberApi.NumberBox(42).getNumber(), 42);
assert.equal(component.numberApi.NumberBox.fromNumber(42).getNumber(), 42);
console.log('npm-sdk exports: 42');
"""


@pytest.mark.parametrize("mode", CLI_MODES, ids=lambda value: f"cli:{value}")
def test_npm_archive_bundle_http_names_strip_validate_execute(
    tmp_path, mode, monkeypatch
):
    monkeypatch.setenv("npm_config_cache", str(tmp_path / ".npm-cache"))
    if not cli_mode_available(mode):
        pytest.skip(f"CLI mode '{mode}' not available")
    if mode != "docker":
        missing = [
            tool
            for tool in ("npm", "npx", "jco", "wasm-tools")
            if not shutil.which(tool)
        ]
        if missing:
            pytest.skip(f"JS toolchain incomplete: {', '.join(missing)}")
    (tmp_path / "wit").mkdir()
    (tmp_path / "wit/world.wit").write_text(WIT)
    sdk = tmp_path / "sdk-package"
    sdk.mkdir()
    (sdk / "package.json").write_text(
        json.dumps(
            {
                "name": "tarawasm-test-sdk",
                "version": "1.0.0",
                "type": "module",
                "exports": "./index.js",
                "bin": {"sdk-check": "./check.js"},
            }
        )
    )
    (sdk / "index.js").write_text(
        "import { offset } from './offset.js';\nexport const add = (a, b) => a + b + offset;\n"
    )
    (sdk / "offset.js").write_text("export const offset = 0;\n")
    (sdk / "check.js").write_text(
        "#!/usr/bin/env node\nconsole.log('SDK archive installed');\n"
    )
    (sdk / "check.js").chmod(0o755)
    (tmp_path / "package.json").write_text('{"type":"module","private":true}')
    run_tool(tmp_path, "npm", "pack", "./sdk-package", "--ignore-scripts", mode=mode)
    run_tool(
        tmp_path,
        "npm",
        "install",
        "./tarawasm-test-sdk-1.0.0.tgz",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
        mode=mode,
    )
    result = run_tool(
        tmp_path,
        "npx",
        "--no-install",
        "sdk-check",
        mode=mode,
        capture_output=True,
        text=True,
    )
    assert "SDK archive installed" in result.stdout
    run_cli(
        tmp_path,
        "init",
        "--lang",
        "js",
        "--wit",
        "wit",
        "--world",
        "sdk",
        ".",
        mode=mode,
    )
    source = (tmp_path / "main.js").read_text()
    bodies = {
        "add-number": "return add(firstNumber, secondNumber);",
        "[constructor]number-box": "this.value = initialValue;",
        "[method]number-box.get-number": "return this.value;",
        "[static]number-box.from-number": "return new NumberBox(initialValue);",
    }
    for name, body in bodies.items():
        marker = f'throw new Error("TODO: implement WIT item {name}");'
        assert marker in source
        source = source.replace(marker, body)
    (tmp_path / "main.js").write_text(
        "import { add } from 'tarawasm-test-sdk';\n" + source
    )
    run_cli(tmp_path, "bind", mode=mode)
    run_cli(tmp_path, "build", "--", "--enable", "http", mode=mode)
    component = "dist/sdk.wasm"
    metadata = run_tool(
        tmp_path,
        "wasm-tools",
        "metadata",
        "show",
        component,
        "--json",
        mode=mode,
        capture_output=True,
        text=True,
    )
    producers = dict(json.loads(metadata.stdout)["component"]["metadata"]["producers"])
    assert producers["processed-by"]["ComponentizeJS"] == "0.23.0"
    imports = run_tool(
        tmp_path,
        "wasm-tools",
        "component",
        "wit",
        component,
        mode=mode,
        capture_output=True,
        text=True,
    )
    assert "wasi:http/" in imports.stdout
    run_cli(tmp_path, "strip", component, "--all", mode=mode)
    run_tool(tmp_path, "wasm-tools", "validate", "dist/sdk.strip.wasm", mode=mode)
    assert (tmp_path / "dist/sdk.strip.wasm").stat().st_size <= (
        tmp_path / component
    ).stat().st_size
    run_tool(
        tmp_path,
        "jco",
        "transpile",
        "dist/sdk.strip.wasm",
        "-o",
        "transpiled",
        "--name",
        "sdk",
        mode=mode,
    )
    (tmp_path / "run.mjs").write_text(RUNNER)
    executed = run_tool(
        tmp_path, "node", "run.mjs", mode=mode, capture_output=True, text=True
    )
    assert "npm-sdk exports: 42" in executed.stdout


def test_js_language_image_has_complete_node_distribution(tmp_path, monkeypatch):
    image = os.environ.get("TARAWASM_JS_DOCKER_IMAGE")
    if not image:
        pytest.skip("TARAWASM_JS_DOCKER_IMAGE is not configured")
    monkeypatch.setenv("TARAWASM_DOCKER_IMAGE", image)
    test_npm_archive_bundle_http_names_strip_validate_execute(
        tmp_path, "docker", monkeypatch
    )

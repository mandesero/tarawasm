"""Build generated starters without replacing their imports or export wiring."""

import re
import subprocess
from pathlib import Path

import pytest
from utils import CLI_MODES, cli_mode_available, run_cli, run_tool

from tarawasm.backends import get_backend

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = {
    "direct": "export add: func(a: s32, b: s32) -> s32;",
    "interface": "export arithmetic;",
    "mixed": "export add: func(a: s32, b: s32) -> s32; export arithmetic;",
    "empty": "",
    "empty-interface": "export marker;",
    "resource-interface": "export handles;",
    "type-interface": "export data;",
    "singleton-tuple": "export roundtrip: func(value: tuple<u32>) -> tuple<u32>;",
    "resource-names": "export first; export first-foo;",
    "keywords": (
        "export %type: func(%class: u32) -> u32; "
        "export %default: func(%class: u32) -> u32; export %class; export %mod;"
    ),
    "inline-interface": "export api: interface { check: func(value: u32) -> u32; }",
    "options": (
        "export check: func(value: option<u32>) -> option<u32>; "
        "export nested: func(value: option<option<u32>>) -> option<option<u32>>; "
        "export text: func(value: option<string>) -> option<string>; export options;"
    ),
    "c-identifiers": (
        "export check: func(int: u32) -> u32; "
        "export text: func(ret: string, err: u32) -> result<string, string>;"
    ),
    "resource-handles": "export borrowed;",
}


class EmptyInterfaceCompilerError(RuntimeError):
    """The specific upstream failure, excluding tarawasm init/bind regressions."""


class DuplicateResourceCompilerError(RuntimeError):
    """ComponentizeJS redeclares resource names in its initializer."""


@pytest.mark.parametrize("mode", CLI_MODES, ids=lambda value: f"cli:{value}")
@pytest.mark.parametrize(
    "language,exports",
    [
        (language, exports)
        for exports in ("direct", "interface", "mixed", "empty")
        for language in ("python", "js", "rust", "go", "c")
    ]
    + [(language, "empty-interface") for language in ("js", "rust", "go", "c")]
    + [
        # componentize-py 0.25.1 / component-init-transform 0.2.0 miscopies an
        # empty nested component: "unknown component 1: component index out of
        # bounds". This is an upstream compiler bug, not an invalid WIT contract.
        # Expected XFAIL keeps CI green; strict=True makes a successful build
        # fail CI as XPASS so the upstream fix cannot go unnoticed. Once the
        # supported compiler is fixed, remove this xfail mark, the diagnostic
        # translation below and EmptyInterfaceCompilerError; keep the test case.
        pytest.param(
            "python",
            "empty-interface",
            marks=pytest.mark.xfail(
                reason="componentize-py: empty exported interface produces an invalid component",
                raises=EmptyInterfaceCompilerError,
                strict=True,
            ),
        )
    ]
    + [(language, "resource-interface") for language in ("go", "rust", "c")]
    + [(language, "keywords") for language in ("python", "js", "rust")]
    + [
        pytest.param(
            "js",
            "resource-names",
            marks=pytest.mark.xfail(
                reason="ComponentizeJS: duplicate resource names in initializer.js",
                raises=DuplicateResourceCompilerError,
                strict=True,
            ),
        ),
        ("rust", "resource-names"),
        ("go", "type-interface"),
        ("rust", "singleton-tuple"),
        ("c", "inline-interface"),
        ("rust", "inline-interface"),
        ("c", "options"),
        ("c", "c-identifiers"),
        ("rust", "resource-handles"),
    ],
)
def test_generated_starter_builds(tmp_path, mode, language, exports, capfd):
    if not cli_mode_available(mode):
        pytest.skip(f"CLI mode '{mode}' not available")
    backend = get_backend(language)
    if mode != "docker" and backend.doctor():
        pytest.skip(f"Local {language} toolchain is incomplete")
    wit = tmp_path / "wit"
    wit.mkdir()
    world = (
        "calculator-world" if (language, exports) == ("c", "direct") else "calculator"
    )
    imports = ""
    if language == "go":
        # TinyGo needs these imports even when the guest exports nothing.
        wasi = (ROOT / "examples/go/wit/adder.wit").read_text()
        imports = "\n".join(re.findall(r"^\s*import wasi:[^;]+;", wasi, re.M))
        (wit / "wasi.wit").write_text(
            "package wasi:" + wasi.split("package wasi:", 1)[1]
        )
    (wit / "calculator.wit").write_text(
        "package example:calculator@0.1.0;\n"
        "interface arithmetic { add: func(a: s32, b: s32) -> s32; }\n"
        "interface marker {}\n"
        "interface borrowed { resource token { constructor(); take: static func(value: borrow<token>); } consume: func(value: borrow<token>); roundtrip: func(value: token) -> token; }\n"
        "interface options { type maybe = option<u32>; check: func(value: maybe) -> maybe; }\n"
        "interface handles { resource token; }\n"
        "interface data { record point { x: s32 } }\n"
        "interface first { resource token { constructor(); } resource foo-token { constructor(); } }\n"
        "interface first-foo { resource token { constructor(); } }\n"
        "interface %class { resource %true { constructor(%class: u32); %async: func(%class: u32) -> u32; } %async: func(%class: u32) -> u32; }\n"
        "interface %mod { %match: func(%class: u32) -> u32; }\n"
        f"world {world} {{ {imports}\n{EXPORTS[exports]} }}\n"
    )
    run_cli(
        tmp_path,
        "init",
        "--lang",
        language,
        "--wit",
        "wit",
        "--world",
        world,
        ".",
        mode=mode,
    )
    source = tmp_path / backend.default_source
    original = source.read_bytes()
    run_cli(tmp_path, "bind", mode=mode)
    try:
        run_cli(tmp_path, "build", mode=mode)
    except subprocess.CalledProcessError as exc:
        if language == "js" and exports == "resource-names":
            captured = capfd.readouterr()
            diagnostic = "redeclaration of let Token"
            if "initializer.js" in captured.err and diagnostic in captured.err:
                raise DuplicateResourceCompilerError(diagnostic) from exc
            raise AssertionError(captured.out + captured.err) from exc
        if language == "python" and exports == "empty-interface":
            captured = capfd.readouterr()
            diagnostic = "unknown component 1: component index out of bounds"
            if diagnostic in captured.err:
                raise EmptyInterfaceCompilerError(diagnostic) from exc
            raise AssertionError(captured.out + captured.err) from exc
        raise
    assert (tmp_path / f"dist/{world}.wasm").is_file()
    assert source.read_bytes() == original
    if (language, exports) == ("c", "direct"):
        run_cli(tmp_path, "build", "--clean", mode=mode)
        assert (tmp_path / f"dist/{world}.wasm").is_file()
    if exports == "resource-interface":
        component = run_tool(
            tmp_path,
            "wasm-tools",
            "print",
            "dist/calculator.wasm",
            mode=mode,
            capture_output=True,
            text=True,
        )
        assert "[dtor]token" in component.stdout

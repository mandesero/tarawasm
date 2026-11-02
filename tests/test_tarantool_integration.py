"""Released SDK + application-owned WIT exports + real Tarantool database calls."""

import http.server
import json
import os
import shutil
import ssl
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest
from utils import CLI_MODES, cli_mode_available, run_cli, run_tool

from tarawasm.backends import get_backend
from tarawasm.backends.base import BackendError
from tarawasm.tarantool import (
    LOCK,
    RUNTIME,
    SDK,
    host_platform,
    release,
    tool_requirements,
)

ROOT = Path(__file__).resolve().parents[1]
RELEASE = os.environ.get("TARAWASM_TARANTOOL_WASM_VERSION") or None
PACKAGE = "acme:orders@1.2.3"
WORLD = "user-service"
LANGUAGES = ("python", "js", "go", "rust", "csharp")
USER_INTERFACE = """interface users {
  record user { id: u32, name: string }
  get: func(id: u32) -> option<user>;
}

"""
LUA = """local wasm = require('wasm')
box.cfg{memtx_dir = arg[1], wal_dir = arg[1], vinyl_dir = arg[1], log_level = 2}
local users = box.schema.space.create('users')
users:create_index('primary')
local module = wasm.load('dist/user-service.wasm', {allow_ip_name_lookup = true})
local app = wasm.bind(module)
if arg[2] ~= 'empty' then
    assert(app['create-user'](7, 'Alice') == 'Alice')
    assert(users:get{7}[2] == 'Alice')
    if arg[3] == 'python' then
        assert(app['ssl-ready']())
        assert(app['dns-ready']())
    end
end
if arg[2] == 'extended' then
    local api = app['acme:orders/users@1.2.3']
    local user = api.get(7)
    assert(user.id == 7 and user.name == 'Alice')
    assert(api.get(999) == nil)
    users:replace{7, 'Bob'}
    assert(api.get(7).name == 'Bob')
end
assert(wasm.drop(module))
if arg[2] == 'extended' and arg[3] == 'python' then
    local function request(bundle, expose)
        local options = {
            inherit_env = false,
            env = {SSL_CERT_FILE = '/certs/' .. bundle},
            allowed_ports = {tonumber(arg[5])},
            allow_ip_name_lookup = true,
        }
        if expose then options.preopened_dirs = {{'./ca', '/certs', perms = 'ro'}} end
        local client = wasm.load('dist/user-service.wasm', options)
        local result = wasm.bind(client)['https-get'](arg[4])
        assert(wasm.drop(client))
        return result
    end
    assert(request('ca.pem', true) == 'urllib3 HTTPS OK')
    assert(request('wrong.pem', true) == 'certificate-rejected')
    assert(request('ca.pem', false) == 'certificate-rejected')
end
print('Tarantool application OK')
os.exit(0)
"""
SOURCES = {
    "python": """import wit_world
from twr_python_sdk import tarantool

# These stdlib dependencies must exist when urllib3 is imported at runtime.
import hmac
import importlib.metadata
import json
import mimetypes
import queue
import zlib

twr_python_sdk.freeze_packages("urllib3")

class WitWorld(wit_world.WitWorld):
    def create_user(self, id: int, name: str) -> str:
        tarantool.space["users"].insert((id, name))
        return name

    def ssl_ready(self) -> bool:
        import ssl
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
        connection = context.wrap_bio(incoming, outgoing, server_hostname="localhost")
        try:
            connection.do_handshake()
        except ssl.SSLWantReadError:
            pass
        return outgoing.pending > 0 and ssl.RAND_status() and len(ssl.RAND_bytes(16)) == 16

    def dns_ready(self) -> bool:
        import asyncio
        import socket

        async def lookup():
            addresses = await asyncio.get_running_loop().getaddrinfo(
                "localhost", 443, family=socket.AF_INET, type=socket.SOCK_STREAM
            )
            return any(address[4] == ("127.0.0.1", 443) for address in addresses)

        return asyncio.run(lookup())

    def https_get(self, url: str) -> str:
        import ssl
        import urllib3

        try:
            with urllib3.PoolManager() as http:
                response = http.request(
                    "GET", url, retries=False,
                    timeout=urllib3.Timeout(connect=5, read=5),
                )
                return response.data.decode("utf-8")
        except urllib3.exceptions.SSLError as error:
            if isinstance(error.args[0], ssl.SSLCertVerificationError):
                return "certificate-rejected"
            raise
""",
    "js": """import {box} from './.tarawasm/tarantool/js/src/index.js';
export function createUser(id, name) {
    box.space('users').insert([id, name]);
    return name;
}
""",
    "go": """package main
import (
    twr "github.com/tarantool/tarantool-wasm-rs/guests/go"
    world "tarawasm/user_service/internal/acme/orders/user-service"
)
func init() {
    world.Exports.CreateUser = func(id uint32, name string) string {
        if _, err := twr.Box.Space("users").Insert([]any{id, name}); err != nil { panic(err) }
        return name
    }
}
func main() {}
""",
    "rust": """#[allow(warnings)]
mod bindings;
struct Component;
impl bindings::Guest for Component {
    fn create_user(id: u32, name: String) -> String {
        let users = tarantool_wasm::Space::by_name("users").unwrap().unwrap();
        users.insert(&(id, &name)).unwrap();
        name
    }
}
bindings::export!(Component with_types_in bindings);
""",
    "csharp": """namespace UserServiceWorld;
public partial class UserServiceWorldExportsImpl : IUserServiceWorldExports {
    public static string CreateUser(uint id, string name) {
        Tarantool.Wasm.Box.Space("users").Insert(id, name);
        return name;
    }
}
""",
}

EXTENSIONS = {
    "python": """
from wit_world import exports
from wit_world.exports.users import User


class Users(exports.Users):
    def get(self, id: int):
        row = tarantool.space["users"].get((id,))
        return None if row is None else User(int(row[0]), row[1])
""",
    "js": """
export const users = {
    get(id) {
        const row = box.space('users').get(id);
        return row == null ? undefined : {id: Number(row[0]), name: row[1]};
    },
};
""",
    "rust": """
impl bindings::exports::acme::orders::users::Guest for Component {
    fn get(id: u32) -> Option<bindings::exports::acme::orders::users::User> {
        let space = tarantool_wasm::Space::by_name("users").unwrap().unwrap();
        space.primary().get(&(id,)).unwrap().map(|tuple| {
            let (id, name): (u32, String) = tuple.decode().unwrap();
            bindings::exports::acme::orders::users::User { id, name }
        })
    }
}
""",
    "go": """
func init() {
    users.Exports.Get = func(id uint32) cm.Option[users.User] {
        row, err := twr.Box.Space("users").Get(id)
        if err != nil { panic(err) }
        if row == nil { return cm.None[users.User]() }
        return cm.Some(users.User{ID: id, Name: row[1].(string)})
    }
}
""",
    "csharp": """using Api = UserServiceWorld.wit.Exports.acme.orders.v1_2_3.IUsersExports;

namespace UserServiceWorld.wit.Exports.acme.orders.v1_2_3;

public partial class UsersExportsImpl : IUsersExports
{
    public static Api.User? Get(uint id)
    {
        var row = Tarantool.Wasm.Box.Space("users").Get(id);
        return row is null ? null : new Api.User(id, row.Get<string>(1));
    }
}
""",
}


def available(language, mode):
    if os.environ.get("TARAWASM_TARANTOOL_IT") != "1":
        pytest.skip("Set TARAWASM_TARANTOOL_IT=1 to download and exercise release SDKs")
    if mode == "standalone":
        if not (ROOT / "target/tarawasm").is_file():
            pytest.skip("Current standalone executable is unavailable")
    elif not cli_mode_available(mode):
        pytest.skip(f"CLI mode {mode} unavailable")
    if mode != "docker":
        missing = get_backend(language).doctor()
        if missing:
            pytest.skip(f"Local {language} toolchain incomplete: {', '.join(missing)}")
        try:
            tool_requirements(language, RELEASE)
        except (BackendError, FileNotFoundError, subprocess.CalledProcessError) as exc:
            pytest.skip(str(exc))
        if not shutil.which("tarantool"):
            pytest.skip("Native Tarantool runtime unavailable")


def invoke(project, mode, *args):
    if mode == "standalone":
        subprocess.run([str(ROOT / "target/tarawasm"), *args], cwd=project, check=True)
    else:
        run_cli(project, *args, mode=mode)


def run_application(project, mode, phase, https_port=None):
    (project / phase).mkdir()
    (project / "check.lua").write_text(LUA)
    language = json.loads((project / LOCK).read_text())["language"]
    arguments = ["check.lua", phase, phase, language]
    if https_port is not None:
        host = "host.docker.internal" if mode == "docker" else "localhost"
        arguments += [f"https://{host}:{https_port}/", str(https_port)]
    if mode == "docker":
        cmd = [
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/amd64",
            *(
                ["--add-host", "host.docker.internal:host-gateway"]
                if https_port
                else []
            ),
            "-v",
            f"{project}:/work",
            "-w",
            "/work",
            "--entrypoint",
            "/usr/bin/env",
            os.environ.get("TARAWASM_TARANTOOL_IMAGE", "tarantool/tarantool:3.7.0"),
            "-u",
            "TT_APP_NAME",
            "-u",
            "TT_INSTANCE_NAME",
            "tarantool",
            *arguments,
        ]
    else:
        cmd = ["tarantool", *arguments]
    result = subprocess.run(
        cmd, cwd=project, check=False, text=True, capture_output=True, timeout=180
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Tarantool application OK" in result.stdout


@contextmanager
def https_server(project, mode):
    """Serve a fixed response with a fresh CA/leaf pair, without public DNS."""
    private = project / "tls"
    private.mkdir()
    ca = project / "ca"
    ca.mkdir()
    (private / "server.ext").write_text(
        "basicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        "subjectAltName=DNS:localhost,DNS:host.docker.internal,IP:127.0.0.1\n"
        "subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n"
    )
    openssl = shutil.which("openssl")
    assert openssl, "OpenSSL executable is required to generate HTTPS test certificates"
    for name in ("ca", "wrong"):
        subprocess.run(
            [
                openssl,
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(private / f"{name}.key"),
                "-out",
                str(ca / f"{name}.pem"),
                "-days",
                "1",
                "-subj",
                f"/CN=Tarawasm {name}",
                "-addext",
                "basicConstraints=critical,CA:TRUE",
                "-addext",
                "keyUsage=critical,keyCertSign,cRLSign",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    subprocess.run(
        [
            openssl,
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(private / "server.key"),
            "-out",
            str(private / "server.csr"),
            "-subj",
            "/CN=localhost",
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    subprocess.run(
        [
            openssl,
            "x509",
            "-req",
            "-in",
            str(private / "server.csr"),
            "-CA",
            str(ca / "ca.pem"),
            "-CAkey",
            str(private / "ca.key"),
            "-CAcreateserial",
            "-out",
            str(private / "server.pem"),
            "-days",
            "1",
            "-extfile",
            str(private / "server.ext"),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    class Handler(http.server.BaseHTTPRequestHandler):
        timeout = 5

        def do_GET(self):
            body = b"urllib3 HTTPS OK"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(
        ("0.0.0.0" if mode == "docker" else "127.0.0.1", 0), Handler
    )
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(private / "server.pem", private / "server.key")
        server.socket = context.wrap_socket(
            server.socket, server_side=True, do_handshake_on_connect=False
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            thread.join(timeout=5)
    finally:
        server.server_close()


def exercise(tmp_path, language, mode):
    available(language, mode)
    project = tmp_path / "application with spaces"
    project.mkdir()
    platform = "linux-x86_64" if mode == "docker" else host_platform()
    invoke(
        project,
        mode,
        "init",
        "--target",
        "tarantool",
        "--lang",
        language,
        "--package",
        PACKAGE,
        "--world",
        WORLD,
        *(["--tarantool-wasm-version", RELEASE] if RELEASE else []),
        "--runtime-platform",
        platform,
        ".",
    )
    wit = project / "wit/app.wit"
    assert "export " not in wit.read_text()
    invoke(project, mode, "bind")
    invoke(project, mode, "build")
    run_application(project, mode, "empty")
    wit.write_text(
        wit.read_text().replace(
            f"world {WORLD} {{",
            f"world {WORLD} {{\n  export create-user: func(id: u32, name: string) -> string;"
            + (
                "\n  export ssl-ready: func() -> bool;\n  export dns-ready: func() -> bool;"
                "\n  export https-get: func(url: string) -> string;"
                if language == "python"
                else ""
            ),
        )
    )
    source = project / get_backend(language).default_source
    if language == "csharp":
        source = project / "src/UserService.cs"
        source.parent.mkdir(exist_ok=True)
    content = SOURCES[language]
    if language == "python":
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--only-binary=:all:",
                "--require-hashes",
                "--target",
                str(project / ".tarawasm/site-packages"),
                "-r",
                str(ROOT / "tests/requirements-tarantool-python.txt"),
            ],
            check=True,
        )
        bootstrap = source.read_text().partition("import wit_world")[0]
        python_spec = release(json.loads((project / LOCK).read_text())["version"]).get(
            "python", {}
        )
        if python_spec.get("ssl_import"):
            assert "twr_python_sdk.install" in bootstrap
        content = bootstrap + content
    source.write_text(content)
    invoke(project, mode, "clean")
    invoke(project, mode, "bind")
    build_args = (
        ["--", "--python-path", ".tarawasm/site-packages"]
        if language == "python"
        else []
    )
    invoke(project, mode, "build", *build_args)
    run_application(project, mode, "initial")
    if language == "python":
        version = json.loads((project / LOCK).read_text())["version"]
        script = release(version).get("python", {}).get("patch_socket_errors")
        if script:
            output = project / "dist" / f"{WORLD}.wasm"
            checked = output.with_name("socket-check.wasm")
            shutil.copy2(output, checked)
            before = checked.read_bytes()
            run_tool(
                project,
                "python3",
                "-I",
                "-B",
                str(SDK / "python" / script),
                str(checked.relative_to(project)),
                mode=mode,
            )
            assert (
                checked.read_bytes() == before
            ), "Build did not apply the SDK socket patch"
            checked.unlink()
    lock_names = [
        LOCK,
        Path("Cargo.lock"),
        Path("Cargo-component.lock"),
        Path("go.mod"),
        Path("go.sum"),
        Path("packages.lock.json"),
    ]
    locks = {
        name: (project / name).read_bytes()
        for name in lock_names
        if (project / name).is_file()
    }
    runtime = (project / RUNTIME).read_bytes()
    wit = project / "wit/app.wit"
    wit.write_text(
        wit.read_text().replace(
            f"world {WORLD} {{", USER_INTERFACE + f"world {WORLD} {{\n  export users;"
        )
    )
    if language == "csharp":
        (project / "src/Users.cs").write_text(EXTENSIONS[language])
    else:
        content = source.read_text()
        if language == "go":
            content = content.replace(
                "import (",
                '''import (
    cm "go.bytecodealliance.org/cm"
    users "tarawasm/user_service/internal/acme/orders/users"''',
            )
        source.write_text(content + EXTENSIONS[language])
    sources = {p: p.read_bytes() for p in [source, wit]}
    # Python's binding generator requires an empty destination. This also proves
    # environment inputs survive the existing clean/regenerate workflow.
    invoke(project, mode, "clean")
    assert (project / RUNTIME).read_bytes() == runtime
    assert (project / SDK).is_dir()
    invoke(project, mode, "bind")
    invoke(project, mode, "build", *build_args)
    if language == "python":
        with https_server(project, mode) as port:
            run_application(project, mode, "extended", https_port=port)
    else:
        run_application(project, mode, "extended")
    assert all(path.read_bytes() == data for path, data in sources.items())
    assert all((project / path).read_bytes() == data for path, data in locks.items())


@pytest.mark.parametrize("mode", CLI_MODES, ids=lambda value: f"cli:{value}")
@pytest.mark.parametrize("language", LANGUAGES, ids=lambda value: f"lang:{value}")
def test_tarantool_sdk_and_user_defined_wit(tmp_path, language, mode):
    exercise(tmp_path, language, mode)


def test_tarantool_standalone_with_extended_wit(tmp_path):
    exercise(tmp_path, "python", "standalone")

#!/bin/bash
set -euo pipefail

# Match the bind-mounted project owner instead of creating root-owned output and
# later making the entire project world-writable.
if [ "$(id -u)" -eq 0 ] && [ -d /work ]; then
    work_uid="$(stat -c '%u' /work)"
    work_gid="$(stat -c '%g' /work)"
    if [ "$work_uid" -ne 0 ]; then
        runtime_home="/tmp/tarawasm-user-${work_uid}"
        mkdir -p "$runtime_home"
        chown "$work_uid:$work_gid" "$runtime_home"
        if ! getent group "$work_gid" >/dev/null; then
            groupadd --gid "$work_gid" tarawasm-host
        fi
        if ! getent passwd "$work_uid" >/dev/null; then
            useradd \
                --uid "$work_uid" \
                --gid "$work_gid" \
                --home-dir "$runtime_home" \
                --no-create-home \
                --shell /bin/bash \
                tarawasm-host
        fi
        export HOME="$runtime_home"
        export CARGO_HOME="$runtime_home/.cargo"
        exec setpriv \
            --reuid="$work_uid" \
            --regid="$work_gid" \
            --init-groups \
            --inh-caps=-all \
            --ambient-caps=-all \
            "$0" "$@"
    fi
fi

PERSISTENT_PY_SITE="${TARAWASM_PY_SITE_PACKAGES:-/work/.tarawasm/site-packages}"
if ! mkdir -p "$PERSISTENT_PY_SITE" 2>/dev/null; then
    PERSISTENT_PY_SITE="/tmp/tarawasm-site-packages"
    mkdir -p "$PERSISTENT_PY_SITE"
fi

export TARAWASM_PY_SITE_PACKAGES="$PERSISTENT_PY_SITE"
export PYTHONPATH="${TARAWASM_PY_SITE_PACKAGES}:/app:${PYTHONPATH:-}"

if [ "${1:-}" == "pip" ]; then
    shift
    if [ "${1:-}" == "install" ]; then
        for arg in "$@"; do
            case "$arg" in
                --target|-t|--target=*|-t=*|--user|--prefix|--prefix=*|--root|--root=*)
                    echo "tarawasm: pip install location is managed at $TARAWASM_PY_SITE_PACKAGES" >&2
                    echo "tarawasm: remove '$arg' or set TARAWASM_PY_SITE_PACKAGES for every install/build invocation" >&2
                    exit 2
                    ;;
            esac
        done
        shift
        exec pip install --target "$TARAWASM_PY_SITE_PACKAGES" "$@"
    fi
    exec pip "$@"
fi

# Keep explicit tarawasm subcommands routed through the CLI module.
case "${1:-}" in
    ""|init|bind|build|clean|all|strip|--help|-h)
        exec python3 -m tarawasm.cli "$@"
        ;;
esac

# Allow explicit tools/commands inside the container when first token resolves to a binary.
if [ -n "${1:-}" ] && [ "$(type -t "$1" || true)" = "file" ]; then
    exec "$@"
fi

exec python3 -m tarawasm.cli "$@"

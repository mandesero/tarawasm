#!/bin/bash
set -euo pipefail

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
        has_target=0
        for arg in "$@"; do
            case "$arg" in
                --target|-t|--target=*|-t=*)
                    has_target=1
                    break
                    ;;
            esac
        done
        if [ "$has_target" -eq 0 ]; then
            shift
            exec pip install --target "$TARAWASM_PY_SITE_PACKAGES" "$@"
        fi
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

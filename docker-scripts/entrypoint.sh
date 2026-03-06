#!/bin/bash
set -euo pipefail

export PYTHONPATH="/app:${PYTHONPATH:-}"

if [ "${1:-}" == "pip" ]; then
    shift
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

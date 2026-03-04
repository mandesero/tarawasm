#!/usr/bin/env bash
set -uo pipefail

declare -A CMD_REQUIRED=(
  [wkg]=0.15.0
  [wasm-tools]=1.245.1
  [cargo-component]=0.21.1
  [jco]=1.17.0
  [componentize-js]=0.19.3
  [wit-bindgen]=0.53.1
)

declare -A NPM_GLOBAL_PACKAGE=(
  [jco]=@bytecodealliance/jco
  [componentize-js]=@bytecodealliance/componentize-js
)

declare -A PIP_REQUIRED=(
  [nuitka]=4.0.2
  [componentize-py]=0.21.0
  [click]=8.3.1
)

declare -A NPM_REQUIRED=(
  [@bytecodealliance/preview2-shim]=0.17.8
)

error_flag=0

version_ge() {
  if [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" == "$2" ]]; then
    return 0
  else
    return 1
  fi
}

npm_global_version() {
  local pkg=$1
  if ! command -v npm &>/dev/null; then
    echo ""
    return
  fi

  local roots=()
  local npm_root
  npm_root=$(npm root -g 2>/dev/null || true)
  [[ -n "$npm_root" ]] && roots+=("$npm_root")

  local npm_prefix
  npm_prefix=$(npm prefix -g 2>/dev/null || true)
  [[ -n "$npm_prefix" ]] && roots+=("${npm_prefix}/lib/node_modules")

  # In CI, npm packages may be installed with sudo under /usr/local while checks run as runner.
  roots+=("/usr/local/lib/node_modules" "/usr/lib/node_modules")

  local pkg_json=""
  local root
  for root in "${roots[@]}"; do
    if [[ -f "${root}/${pkg}/package.json" ]]; then
      pkg_json="${root}/${pkg}/package.json"
      break
    fi
  done

  if [[ -z "$pkg_json" ]]; then
    echo ""
    return
  fi

  python3 - "$pkg_json" 2>/dev/null <<'PY' || true
import json
import sys

path = sys.argv[1]

try:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
except Exception:
    print("")
    raise SystemExit(0)

print(obj.get("version", ""))
PY
}

check_cmd() {
  local cmd=$1
  local need=${CMD_REQUIRED[$cmd]}

  if ! command -v "$cmd" &>/dev/null; then
    printf "%-18s >=%-8s %-6s %s\n" "$cmd" "$need" "ERROR" "not installed"
    error_flag=1
    return
  fi

  local found
  found=""
  local npm_pkg=${NPM_GLOBAL_PACKAGE[$cmd]:-}

  # For npm-backed CLIs prefer package version from npm metadata.
  if [[ -n "$npm_pkg" ]] && command -v npm &>/dev/null; then
    found=$(npm_global_version "$npm_pkg" || true)
  fi

  if [[ -z "$found" ]]; then
    local raw
    raw=$("$cmd" --version 2>&1 || true)
    found=$(echo "$raw" | grep -Eo '[0-9]+(\.[0-9]+){1,2}' | head -n1 || true)
  fi

  if [[ -z "$found" ]]; then
    printf "%-18s >=%-8s %-6s %s\n" "$cmd" "$need" "ERROR" "cannot parse version"
    error_flag=1
    return
  fi

  if version_ge "$found" "$need"; then
    printf "%-18s >=%-8s %-6s %s\n" "$cmd" "$need" "OK" "$found"
  else
    printf "%-18s >=%-8s %-6s %s (found %s)\n" \
      "$cmd" "$need" "ERROR" "" "$found"
    error_flag=1
  fi
}

check_pip() {
  local pkg=$1
  local need=${PIP_REQUIRED[$pkg]}

  if ! pip3 show "$pkg" &>/dev/null; then
    printf "%-18s >=%-8s %-6s %s\n" "$pkg" "$need" "ERROR" "not installed"
    error_flag=1
    return
  fi

  local found
  found=$(pip3 show "$pkg" | awk '/^Version:/ {print $2}')

  if [[ -z "$found" ]]; then
    printf "%-18s >=%-8s %-6s %s\n" "$pkg" "$need" "ERROR" "cannot parse version"
    error_flag=1
    return
  fi

  if version_ge "$found" "$need"; then
    printf "%-18s >=%-8s %-6s %s\n" "$pkg" "$need" "OK" "$found"
  else
    printf "%-18s >=%-8s %-6s %s (found %s)\n" \
      "$pkg" "$need" "ERROR" "" "$found"
    error_flag=1
  fi
}

check_npm() {
  local pkg=$1
  local need=${NPM_REQUIRED[$pkg]}

  if ! command -v npm &>/dev/null; then
    printf "%-18s >=%-8s %-6s %s\n" "$pkg" "$need" "ERROR" "npm not installed"
    error_flag=1
    return
  fi

  local found
  found=$(npm_global_version "$pkg" || true)

  if [[ -z "$found" ]]; then
    printf "%-18s >=%-8s %-6s %s\n" "$pkg" "$need" "ERROR" "not installed"
    error_flag=1
    return
  fi

  if version_ge "$found" "$need"; then
    printf "%-18s >=%-8s %-6s %s\n" "$pkg" "$need" "OK" "$found"
  else
    printf "%-18s >=%-8s %-6s %s (found %s)\n" \
      "$pkg" "$need" "ERROR" "" "$found"
    error_flag=1
  fi
}

printf "%-18s %-10s %-6s %s\n" "Tool/Package" "Required" "Status" "Details"
width=$(printf "%-18s %-10s %-6s %s\n" "Tool/Package" "Required" "Status" "Details" | wc -c)
printf '%*s\n' "$width" '' | tr ' ' '-'

for cmd in "${!CMD_REQUIRED[@]}"; do
  check_cmd "$cmd"
done

for pkg in "${!PIP_REQUIRED[@]}"; do
  check_pip "$pkg"
done

for pkg in "${!NPM_REQUIRED[@]}"; do
  check_npm "$pkg"
done

exit $error_flag

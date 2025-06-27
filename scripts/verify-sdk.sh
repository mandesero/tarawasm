#!/usr/bin/env bash
set -euo pipefail

declare -A CMD_REQUIRED=(
  [wkg]=0.10.0
  [wasm-tools]=1.0.43
  [cargo-component]=0.21.1
  [jco]=1.9.1
  [wit-bindgen]=0.39.0
)

declare -A PIP_REQUIRED=(
  [nuitka]=2.7.2
  [componentize-py]=0.17.0
  [click]=8.1.7
)

error_flag=0

version_ge() {
  if [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" == "$2" ]]; then
    return 0
  else
    return 1
  fi
}

check_cmd() {
  local cmd=$1
  local need=${CMD_REQUIRED[$cmd]}

  if ! command -v "$cmd" &>/dev/null; then
    printf "%-18s >=%-8s %-6s %s\n" "$cmd" "$need" "ERROR" "not installed"
    error_flag=1
    return
  fi

  local raw
  raw=$("$cmd" --version 2>&1)
  local found
  found=$(echo "$raw" | grep -Eo '[0-9]+(\.[0-9]+){1,2}' | head -n1 || true)

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

printf "%-18s %-10s %-6s %s\n" "Tool/Package" "Required" "Status" "Details"
width=$(printf "%-18s %-10s %-6s %s\n" "Tool/Package" "Required" "Status" "Details" | wc -c)
printf '%*s\n' "$width" '' | tr ' ' '-'

for cmd in "${!CMD_REQUIRED[@]}"; do
  check_cmd "$cmd"
done

for pkg in "${!PIP_REQUIRED[@]}"; do
  check_pip "$pkg"
done

exit $error_flag

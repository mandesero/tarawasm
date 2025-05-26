#!/usr/bin/env bash
set -euo pipefail

declare -A REQUIRED_VERSIONS=(
  [go]=1.20.0
  [rustc]=1.84.1
  [tinygo]=0.37.0
  [node]=20.0.0
  [python3]=3.10.0
)

error_flag=0

version_ge() {
  if [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" == "$2" ]]; then
    return 0
  else
    return 1
  fi
}

check_tool() {
  local cmd=$1
  local ver_arg=$2
  local need=${REQUIRED_VERSIONS[$cmd]}

  if ! command -v "$cmd" &>/dev/null; then
    printf "%-10s >=%-9s %-6s %s\n" "$cmd" "$need" "ERROR" "not installed"
    error_flag=1
    return
  fi

  local raw=$($cmd $ver_arg 2>&1)
  local found=$(echo "$raw" | grep -Eo '[0-9]+(\.[0-9]+){1,2}' | head -n1 || true)

  if [[ -z "$found" ]]; then
    printf "%-10s >=%-9s %-6s %s\n" "$cmd" "$need" "ERROR" "cannot parse '$raw'"
    error_flag=1
    return
  fi

  if version_ge "$found" "$need"; then
    printf "%-10s >=%-9s %-6s %s\n" "$cmd" "$need" "OK" "$found"
  else
    printf "%-10s >=%-9s %-6s %s (found %s)\n" \
      "$cmd" "$need" "ERROR" "" "$found"
    error_flag=1
  fi
}

printf "%-10s %-10s %-6s %s\n" "Tool" "Required" "Status" "Details"
width=$(printf "%-10s %-10s %-6s %s" "Tool" "Required" "Status" "Details" | wc -c)
printf '%*s\n' "$width" '' | tr ' ' '-'

check_tool go       version
check_tool rustc    --version
check_tool tinygo   version
check_tool node     --version
check_tool python3  --version

exit $error_flag

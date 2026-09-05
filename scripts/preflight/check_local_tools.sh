#!/usr/bin/env bash
set -euo pipefail

missing=0
python_command="${PYTHON_BIN:-python3}"
check_command() {
  local command="$1"
  if command -v "$command" >/dev/null 2>&1; then
    printf 'OK   %-12s %s\n' "$command" "$(command -v "$command")"
  else
    printf 'MISS %-12s install before the cloud deployment phase\n' "$command"
    missing=$((missing + 1))
  fi
}

printf '%s\n' 'Healthcare pipeline Phase 0 preflight'
check_command "$python_command"
check_command git
check_command terraform
check_command az
check_command docker
check_command databricks
check_command snow

printf '\nVersions detected:\n'
"$python_command" --version 2>&1 || true
git --version 2>&1 || true
terraform version 2>&1 | head -1 || true
az version --output json 2>/dev/null | head -8 || true
docker --version 2>&1 || true
databricks --version 2>&1 || true
snow --version 2>&1 || true

if [[ "$missing" -gt 0 ]]; then
  printf '\nPreflight incomplete: %d command(s) missing.\n' "$missing"
  exit 1
fi
python_version="$($python_command -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
if ! "$python_command" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  printf '\nPython %s is unsupported; Python 3.10+ is required (3.11 recommended).\n' "$python_version"
  exit 1
fi
printf '\nPreflight passed.\n'

#!/usr/bin/env bash
set -euo pipefail

# Static Terraform check only: never initializes a backend or contacts Azure.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
terraform_bin="${TERRAFORM_BIN:-terraform}"

if ! command -v "$terraform_bin" >/dev/null 2>&1 && [[ ! -x "$terraform_bin" ]]; then
  echo "Terraform executable not found: $terraform_bin" >&2
  exit 1
fi

"$terraform_bin" fmt -check -recursive "$repo_root/infra"
"$terraform_bin" -chdir="$repo_root/infra/environments/demo" init -backend=false -input=false -upgrade=false
"$terraform_bin" -chdir="$repo_root/infra/environments/demo" validate

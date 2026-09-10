#!/usr/bin/env bash
set -euo pipefail

# Plan can refresh Azure state but cannot create, update, or delete resources.
# Apply is deliberately not included in this script.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
terraform_bin="${TERRAFORM_BIN:-terraform}"
tf_dir="${1:-$repo_root/infra/environments/demo}"
vars_file="${2:-demo.tfvars}"
plan_file="${3:-tfplan}"

[[ -d "$tf_dir" ]] || { echo "Terraform directory not found: $tf_dir" >&2; exit 1; }
[[ -f "$tf_dir/$vars_file" ]] || {
  echo "Variables file not found: $tf_dir/$vars_file" >&2
  echo "Copy demo.tfvars.example to demo.tfvars and inject secrets via environment variables." >&2
  exit 1
}
case "$plan_file" in
  /*) ;;
  *) plan_file="$tf_dir/$plan_file" ;;
esac

"$terraform_bin" -chdir="$tf_dir" init -input=false
"$terraform_bin" -chdir="$tf_dir" plan -input=false -lock-timeout=60s \
  -var-file="$vars_file" -out="$plan_file"
printf 'Plan written to %s. Review it before any separately authorized apply.\n' "$plan_file"

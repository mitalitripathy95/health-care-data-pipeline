#!/usr/bin/env bash
set -euo pipefail

# Destruction is intentionally opt-in and interactive. This script never guesses
# the subscription, environment, or variable file.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
terraform_bin="${TERRAFORM_BIN:-terraform}"
tf_dir="${1:-$repo_root/infra/environments/demo}"
vars_file="${2:-demo.tfvars}"

[[ "${DESTROY_HEALTHCARE_DEMO:-}" == "YES" ]] || {
  echo 'Refusing destroy: set DESTROY_HEALTHCARE_DEMO=YES explicitly.' >&2
  exit 1
}
[[ -d "$tf_dir" && -f "$tf_dir/$vars_file" ]] || {
  echo "Terraform directory or variables file missing: $tf_dir/$vars_file" >&2
  exit 1
}

printf 'This will destroy all resources managed by %s using %s.\n' "$tf_dir" "$vars_file"
read -r -p 'Type the exact resource environment name (demo) to continue: ' confirmation
[[ "$confirmation" == demo ]] || { echo 'Destroy cancelled.'; exit 1; }

"$terraform_bin" -chdir="$tf_dir" destroy -input=false -var-file="$vars_file"

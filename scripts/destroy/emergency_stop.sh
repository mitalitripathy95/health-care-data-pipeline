#!/usr/bin/env bash
set -euo pipefail

# Emergency stop is intentionally explicit and requires the operator to pass
# the Terraform environment directory. It never guesses a subscription.
terraform_dir="${1:-infra/environments/demo}"
if [[ ! -d "$terraform_dir" ]]; then
  echo "Terraform directory not found: $terraform_dir" >&2
  exit 1
fi
cat <<'MSG'
Emergency stop checklist:
1. Stop/cancel active ADF and Databricks runs in Azure Portal.
2. Suspend the Snowflake warehouse (ALTER WAREHOUSE <name> SUSPEND).
3. Run the reviewed Terraform destroy from the demo environment directory.
MSG
read -r -p "Type DESTROY to print the destroy command: " confirmation
if [[ "$confirmation" != DESTROY ]]; then
  echo 'Emergency stop cancelled.'
  exit 1
fi
printf 'terraform -chdir=%q destroy -var-file=demo.tfvars\n' "$terraform_dir"

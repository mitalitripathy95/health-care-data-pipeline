#!/usr/bin/env bash
set -euo pipefail

# Cost gate: this script does not deploy anything. It verifies the operator has
# explicitly selected the short-lived demo profile before Terraform is run.
profile="${DATA_PROFILE:-tiny}"
environment="${PIPELINE_ENV:-local}"
location="${AZURE_LOCATION:-eastus}"

case "$profile" in
  tiny|small) ;;
  *) echo "Unsupported DATA_PROFILE=$profile; use tiny or small." >&2; exit 1 ;;
esac
if [[ "$environment" != "demo" && "$environment" != "local" ]]; then
  echo "PIPELINE_ENV must be local or demo; refusing to continue." >&2
  exit 1
fi
printf 'Cost preflight (no deployment)\n'
printf '  environment: %s\n  location:    %s\n  profile:     %s\n' "$environment" "$location" "$profile"
printf '%s\n' '  max runtime: 48 hours (operator enforced)' 
printf '%s\n' '  required: budget alert, tiny profile first, destroy plan reviewed'
if [[ "$profile" == small ]]; then
  echo 'WARNING: small profile may consume trial credits quickly; capture a fresh estimate before apply.' >&2
fi

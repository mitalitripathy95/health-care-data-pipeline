# Phase 0 — Foundation

## Scope

Phase 0 establishes a reproducible local development contract before Azure resources are created.

## Runtime contract

- Python: 3.10 or newer (3.11 recommended)
- Terraform: version pinned in Phase 2 bootstrap
- Azure CLI: authenticated with the intended trial subscription only when deployment begins
- Databricks CLI: v1+ with workspace authentication configured later
- Snowflake CLI: installed and configured later; no credentials in files
- Docker: required for the synthetic generator image

## Validation gates

1. `make check` passes.
2. `make preflight` passes before Phase 2.
3. `bash scripts/preflight/check_no_secrets.sh` passes.
4. The operator confirms the Azure trial subscription, region, and Snowflake trial separately.

## Operational runbooks

- Tool installation and Azure login: `docs/runbooks/phase-0-tool-installation.md`
- Cost gate and teardown: `docs/cost/phase-0-cost-and-teardown.md`
- GitHub OIDC and protected environments: `docs/security/github-oidc.md`

The cost gate is intentionally local and non-deploying. It must be run before
Terraform initialization/plan, and a reviewed destroy plan must exist before
any billable resource is created.

## Naming and tagging

The canonical resource prefix will be `hcpipe-<environment>-<unique_suffix>`. Terraform will apply:

- `project=healthcare-data-pipeline`
- `environment=demo`
- `owner=portfolio`
- `managed_by=terraform`
- `cost_center=trial`
- `data_classification=synthetic`

The unique suffix must not contain credentials or personally identifying information.

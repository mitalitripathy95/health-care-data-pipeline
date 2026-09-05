# Phase 0 cost and teardown gate

## Budget assumptions

The demonstration targets a 1–2 day run on an Azure trial subscription. The
$200 trial balance is an estimate, not a guarantee; Azure pricing, region,
quotas, taxes, and Snowflake trial terms vary. Snowflake credits are separate
from Azure credits.

The required operating profile is **tiny first**. Compute is created only after
an explicit cost review, and the **small** profile is permitted only after a
fresh Azure estimate. Databricks uses job clusters rather than all-purpose
clusters, and Snowflake uses an X-Small warehouse with 60-second auto-suspend.

## Pre-apply gate

```bash
export PIPELINE_ENV=demo DATA_PROFILE=tiny AZURE_LOCATION=eastus
bash scripts/cost/preflight.sh
terraform -chdir=infra/environments/demo init
terraform -chdir=infra/environments/demo plan -out=tfplan
```

Review the plan for SKU, node count, public IPs, private endpoints, and
retention settings. Do not apply if a resource is unexpectedly large or if the
budget alert is absent.

## Teardown order

1. Stop ADF triggers and cancel active pipeline runs.
2. Stop Databricks jobs and clusters.
3. Export run manifests, DQ results, KPI evidence, and cost evidence.
4. Suspend Snowflake warehouses and remove demo tables/stages if required by
   the Snowflake trial policy.
5. Run `terraform plan -destroy`, review it, then run `terraform destroy`.
6. Confirm in Azure Cost Management and the portal that billable resources are
   deleted or stopped. Check for soft-deleted vaults and retained storage.
7. Verify no GitHub secret or local `.env` was created in the repository.

For an urgent stop, run:

```bash
bash scripts/destroy/emergency_stop.sh infra/environments/demo
```

Terraform does not remove every Snowflake account-level object automatically;
Snowflake account cleanup is a separate manual verification step.

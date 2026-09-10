# Demo Azure Terraform environment

This stack prepares the short-lived, synthetic-data demonstration environment. It does
not deploy Snowflake objects; Snowflake is an external account and will be configured in
a later phase using secrets supplied at runtime.

## Cost and safety defaults

- `tiny` profile is the default and only recommended trial profile.
- PostgreSQL uses Burstable B1ms and Azure SQL uses Basic for `tiny`.
- Databricks is a trial workspace; transformation job clusters will be defined later.
- Storage is LRS and monitoring retention is intentionally short.
- Public network access is enabled temporarily to avoid private networking cost and
  complexity. Firewall allowlists and managed identity hardening are later deployment
  tasks; do not load real data.
- No resource is created until `terraform plan` has been reviewed.

## Deploy later, when all phases are coded

```bash
cp demo.tfvars.example demo.tfvars
# Edit demo.tfvars and replace the example suffix. Keep demo.tfvars ignored.
az login
az account set --subscription "$AZURE_SUBSCRIPTION_ID"
export TF_VAR_subscription_id="$AZURE_SUBSCRIPTION_ID"
export TF_VAR_tenant_id="$AZURE_TENANT_ID"
export TF_VAR_sql_admin_login="hcpipeadmin"
export TF_VAR_sql_admin_password='<generated-password>'
export TF_VAR_postgres_admin_password='<generated-password>'
export TF_VAR_alert_email='you@example.com'

bash scripts/terraform/fmt_validate.sh
# After Azure login and after reviewing all remaining application code:
./scripts/terraform/plan_safe.sh infra/environments/demo demo.tfvars tfplan
# Apply only after the final end-to-end code review (manual command, intentionally not
# included in automation):
terraform -chdir=infra/environments/demo apply tfplan
```

Never commit `terraform.tfvars`, `*.tfstate`, plan files, passwords, or Azure tokens.

This is a code-only Phase 2 stack until the final end-to-end review. Local Terraform
commands are static checks only; the runtime (databases, ADF, Databricks, Container Apps,
and ADLS) is Azure-only. Public endpoints are temporary trial controls for synthetic data;
production should use private networking, private endpoints, and VPN/ExpressRoute. Set a
stable `budget_start_date` explicitly when deploying. Destroy the resource group with the
approved guarded teardown script immediately after testing.

## Static checks and teardown guard

From the repository root, the following commands do not create Azure resources:

```bash
TERRAFORM_BIN=/tmp/terraform-bin/terraform bash scripts/terraform/fmt_validate.sh
bash -n scripts/terraform/*.sh
```

A plan is read-only but requires Azure credentials and a populated, ignored `demo.tfvars`:

```bash
./scripts/terraform/plan_safe.sh infra/environments/demo demo.tfvars tfplan
```

Teardown is deliberately interactive and requires an explicit environment variable:

```bash
DESTROY_HEALTHCARE_DEMO=YES ./scripts/terraform/destroy_safe.sh
```
The teardown script is the recommended path after testing; review the plan/state and
confirm that the selected subscription is the disposable demonstration subscription.

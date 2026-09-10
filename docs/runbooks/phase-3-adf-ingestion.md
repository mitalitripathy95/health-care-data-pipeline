# Runbook — Phase 3 ADF Bronze ingestion

## Important status

This is a future Azure deployment and runtime-test procedure. Phase 3 is implemented as
code, but no Azure resources have been deployed and none of the commands or verification
queries below have been executed against Azure. Run this only during the final end-to-end
phase after account values, cost controls, and all later-phase artifacts are ready.

## Prerequisites

- An active Azure trial subscription with sufficient quota and an approved deployment
  region.
- Phase 1 source/container artifacts and Phase 2 Terraform configuration completed.
- Unique, non-production Terraform names and secure CI/CD credentials.
- Budget alerts reviewed before creating compute.
- Only synthetic data; never load real PHI.
- The ADF schedule remains disabled (`enable_adf_schedule_trigger = false`).

## 1. Perform static checks before deployment

From the repository root:

```bash
/tmp/terraform-bin/terraform fmt -check -recursive infra
(
  cd infra/environments/demo
  /tmp/terraform-bin/terraform init -backend=false
  /tmp/terraform-bin/terraform validate
)
.venv311/bin/python scripts/adf/validate_artifacts.py .
.venv311/bin/python -m pytest
.venv311/bin/ruff check .
.venv311/bin/ruff format --check .
bash scripts/preflight/check_no_secrets.sh
git -c safe.directory="$PWD" diff --check
```

Resolve every failure. Review the Terraform plan and projected cost before apply. Do not
apply only Phase 3 in isolation if later phases are required for the demonstration.

## 2. Deploy infrastructure in the final deployment phase

Use the final CI/CD workflow or the documented Terraform procedure to initialize the
remote backend, plan, obtain approval, and apply. Keep these defaults unless the plan has
been explicitly reviewed:

```hcl
enable_adf_schedule_trigger = false
data_profile                = "tiny"
```

Record the deployment outputs, ADF name, source endpoints, Key Vault name, storage
account, filesystem, and Azure SQL database. Do not place credentials in Terraform
variables, shell history, logs, or GitHub Actions output.

## 3. Populate Key Vault

Create these secrets using the approved secure deployment process:

- `adf-postgresql-connection-string`
- `adf-azure-sql-connection-string`

The connection strings must enforce encryption and contain least-privilege synthetic-source
accounts. ADF retrieves them through `ls_key_vault`; do not paste them into linked-service
JSON. Confirm that the ADF managed identity can read only the required secrets.

## 4. Install control objects and metadata

Connect securely to the Azure SQL database and execute, in order:

1. `database/azure_sql/ddl/002_control_schema.sql`
2. `database/azure_sql/seed/001_ingestion_config.sql`

Both scripts are designed to be rerunnable. Confirm 2 source systems and 19 enabled table
configurations, including exactly 2 full tables:

```sql
SELECT source_system_id, source_name, engine, enabled
FROM control.source_system
ORDER BY source_system_id;

SELECT load_type, COUNT(*) AS table_count
FROM control.ingestion_config
WHERE enabled = 1
GROUP BY load_type;

SELECT s.source_name, c.source_schema, c.source_table,
       c.load_type, c.primary_key_column, c.watermark_column
FROM control.ingestion_config AS c
JOIN control.source_system AS s
  ON s.source_system_id = c.source_system_id
WHERE c.enabled = 1
ORDER BY s.source_name, c.source_schema, c.source_table;
```

Expected metadata totals are 17 `INCREMENTAL` and 2 `FULL` rows. The full tables are
`clinical.medications` and `payer.plans`.

## 5. Wait for identity and RBAC propagation

Azure role assignments may take several minutes to propagate. Before treating a linked
service failure as a configuration defect, wait for propagation and verify:

- ADF identity can retrieve the two Key Vault secrets.
- ADF identity can create files beneath the ADLS filesystem.
- Source database firewall/network rules permit the Azure integration runtime.
- TLS and database account permissions are correct.

## 6. Test linked services and datasets

In ADF Studio, without enabling the schedule:

1. Test `ls_key_vault`.
2. Test `ls_postgresql_clinical`.
3. Test `ls_azure_sql_payer`.
4. Test `ls_adls_lake`.
5. Preview one parameterized source dataset from each source.

Do not expose a connection string in screenshots or copied diagnostics.

## 7. Run initial ingestion manually

Execute `pl_master_ingestion` with a globally unique batch ID, for example:

```text
batch_id=initial-20260907-001
source_filter=ALL
backfill_start=
backfill_end=
```

Wait for completion and retain the ADF pipeline RunId. Do not enable
`tr_daily_ingestion`. The master must succeed only after all 19 child table runs publish.

## 8. Verify the run

Use Azure SQL to inspect the audit records:

```sql
DECLARE @batch_id VARCHAR(100) = 'initial-20260907-001';

SELECT *
FROM control.pipeline_run
WHERE batch_id = @batch_id;

SELECT s.source_name, c.source_schema, c.source_table,
       tr.status, tr.row_count, tr.file_count, tr.bronze_path,
       tr.low_watermark_ts, tr.low_watermark_key,
       tr.high_watermark_ts, tr.high_watermark_key,
       tr.error_message
FROM control.table_run AS tr
JOIN control.pipeline_run AS pr ON pr.pipeline_run_id = tr.pipeline_run_id
JOIN control.ingestion_config AS c
  ON c.ingestion_config_id = tr.ingestion_config_id
JOIN control.source_system AS s
  ON s.source_system_id = c.source_system_id
WHERE pr.batch_id = @batch_id
ORDER BY s.source_name, c.source_schema, c.source_table;

SELECT *
FROM control.batch_manifest
WHERE batch_id = @batch_id
ORDER BY published_at;

SELECT *
FROM control.job_dependency
WHERE batch_id = @batch_id;
```

Verify all of the following:

- One successful pipeline run and 19 successful table runs exist.
- Every successful table run has exactly one published manifest.
- Source and landed row counts match.
- Non-empty outputs have `file_count > 0`.
- Every ADLS path follows
  `bronze/raw/source=.../schema=.../table=.../batch_id=.../run_id=.../`.
- The dependency row is `adf_ingestion -> databricks_bronze`, status `READY`.
- No ingestion locks remain:

```sql
SELECT * FROM control.ingestion_lock;
```

## 9. Test duplicate-batch protection

Run `pl_master_ingestion` again with the exact successful batch ID. It must fail in
`control.usp_begin_pipeline_run` and must not publish new manifests or move watermarks.
Use a new batch ID for every legitimate rerun.

## 10. Test equal-timestamp key handling

Load the synthetic incremental fixture in which at least two changed rows share one
watermark timestamp but have different primary keys. Run a new ingestion batch. Confirm
both keys are present in the Parquet output and the committed high tuple uses the greatest
ordered `(timestamp, key)` value. This proves the pipeline does not use a timestamp-only
predicate.

## 11. Test partial failure and recovery

1. Temporarily cause one safe, reversible table failure, such as removing that test
   account's read permission.
2. Run a unique batch and confirm the master fails.
3. Confirm the table is `FAILED`, its lock was released, it has no published manifest,
   its watermark is unchanged, and no downstream `READY` row exists for the batch.
4. Restore the permission.
5. Rerun with a **new** batch ID.
6. Confirm extraction resumes from the last successfully committed watermark and publishes
   normally.

Never delete audit records to simulate recovery.

## 12. Test a bounded backfill

Run a unique batch with both backfill bounds populated, for example:

```text
batch_id=backfill-2026-08-01-2026-08-02-001
source_filter=member_claims
backfill_start=2026-08-01T00:00:00.000
backfill_end=2026-08-02T00:00:00.000
```

Capture `control.watermark_state` before and after. Confirm the backfill writes a distinct
immutable path and manifest but does not change the production watermark:

```sql
SELECT c.ingestion_config_id, s.source_name, c.source_schema, c.source_table,
       w.watermark_ts, w.watermark_key, w.updated_at
FROM control.watermark_state AS w
JOIN control.ingestion_config AS c
  ON c.ingestion_config_id = w.ingestion_config_id
JOIN control.source_system AS s
  ON s.source_system_id = c.source_system_id
ORDER BY c.ingestion_config_id;
```

## 13. Keep scheduling disabled

Do not activate `tr_daily_ingestion` during one-off testing. If schedule behavior must be
demonstrated, enable it only through reviewed Terraform, observe one expected execution,
and disable it immediately afterward.

## 14. Evidence and teardown

Capture sanitized evidence: Terraform plan summary, ADF run/activity status, control-table
counts, ADLS paths, manifest counts, failure recovery, and unchanged backfill watermarks.
Never capture secrets or connection strings.

After the complete project demonstration:

1. Disable ADF triggers and any later-phase schedules.
2. Export only approved, non-sensitive logs/evidence.
3. Run and review a Terraform destroy plan.
4. Destroy all project resources.
5. Confirm the resource group and billable dependent resources are gone.
6. Check Azure Cost Management for delayed charges.

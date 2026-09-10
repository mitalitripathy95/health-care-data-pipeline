# Runbook — Phase 4 Databricks Bronze

## Important status

This is a future deployment and runtime-test procedure. Phase 4 code and static checks are
implemented, but Azure/Databricks deployment and runtime testing have not occurred. Do not
run deployment commands until all project phases, account prerequisites, budget controls,
and secure values are ready.

## Prerequisites

- Phase 1 synthetic source data, Phase 2 infrastructure, and Phase 3 ADF artifacts are
  complete.
- The Azure Databricks workspace and access connector are created by the final Terraform
  deployment.
- The workspace is attached to a Unity Catalog metastore.
- A catalog (default `healthcare_demo`), Bronze schema, quarantine schema, storage
  credential, and external locations exist with least-privilege grants to the job identity.
- An Azure Key Vault-backed Databricks secret scope exists with `control-db-user` and
  `control-db-password`.
- The control JDBC URL uses encrypted Azure SQL connectivity.
- ADF has published all expected manifests and the READY dependency for the selected
  batch.
- Only synthetic data is present and Azure budget alerts are active.

## 1. Static validation before cloud deployment

From the repository root:

```bash
.venv311/bin/python scripts/databricks/validate_bundle.py .
.venv311/bin/python -m pytest tests/unit/bronze -q
.venv311/bin/ruff check databricks/src scripts/databricks tests/unit/bronze
.venv311/bin/ruff format --check databricks/src scripts/databricks tests/unit/bronze
bash scripts/preflight/check_no_secrets.sh
git -c safe.directory="$PWD" diff --check
```

The validator confirms the wheel task, parameters, variables, least-privilege permission
shape, absent/paused schedule, single-node compute, auto-termination, concurrency limit,
and absence of common plaintext credential assignments.

## 2. Obtain final deployment values

After the approved Terraform apply, retrieve `databricks_workspace_url`. Confirm that the
configured small Azure node type and pinned Databricks Runtime LTS value are available in
the deployment region. Override them rather than changing cost controls if the defaults
are unavailable.

Create a local, uncommitted bundle variable file or pass CI/CD variables securely. At
least one metadata source must be configured:

- recommended: `control_jdbc_url` for direct Azure SQL manifests and dependency updates;
- controlled test alternative: `manifest_path` for an enriched Delta metadata feed.

Do not commit URLs containing credentials. The JDBC URL must not contain a username or
password.

## 3. Validate the bundle against the workspace

Authenticate through the approved Azure identity flow, then run:

```bash
cd databricks
databricks bundle validate -t demo \
  --var="workspace_host=<terraform-databricks-workspace-url>" \
  --var="control_jdbc_url=<encrypted-azure-sql-jdbc-url>"
```

Validation may expose missing account-level Unity Catalog prerequisites. Fix grants or
bindings; do not add broad workspace administrator permissions to the job.

## 4. Deploy during the final deployment phase

```bash
cd databricks
databricks bundle deploy -t demo \
  --var="workspace_host=<terraform-databricks-workspace-url>" \
  --var="control_jdbc_url=<encrypted-azure-sql-jdbc-url>"
```

Verify that the deployed job has no schedule, uses only an ephemeral job cluster, has
`max_concurrent_runs=1`, uses the standard runtime engine, and auto-terminates after 15
minutes. Do not create an interactive all-purpose cluster.

## 5. Run one explicit ADF-published batch

Use the exact Phase 3 batch ID:

```bash
cd databricks
databricks bundle run wf_bronze_ingestion -t demo \
  --var="workspace_host=<terraform-databricks-workspace-url>" \
  --var="control_jdbc_url=<encrypted-azure-sql-jdbc-url>" \
  --params="batch_id=<published-batch-id>,source_filter=ALL"
```

Keep the job run ID. The job must not discover arbitrary ADLS folders; it must select only
published/reconciled manifests with the READY dependency.

## 6. Runtime acceptance checks

In Databricks SQL or an approved query surface, verify:

```sql
SELECT status, COUNT(*)
FROM healthcare_demo.bronze._bronze_batch_registry
WHERE batch_id = '<published-batch-id>'
GROUP BY status;

SELECT source_system, source_schema, source_table,
       input_rows, output_rows, quarantined_rows, file_count,
       schema_version, drift_kind, status, error_message
FROM healthcare_demo.bronze._bronze_processing_audit
WHERE batch_id = '<published-batch-id>'
ORDER BY source_system, source_schema, source_table;
```

Expected initial acceptance:

- 19 successful registry/audit results for an `ALL` batch;
- Bronze row counts equal manifest counts minus quarantined corrupt rows;
- every target includes all nine ingestion metadata columns;
- target names follow `<source>_<schema>_<table>`;
- no real PHI or plaintext credential appears in data, logs, configuration, or tables;
- the cluster terminates after the run.

In Azure SQL, confirm:

```sql
SELECT batch_id, upstream_job, downstream_job, status, updated_at
FROM control.job_dependency
WHERE batch_id = '<published-batch-id>'
ORDER BY upstream_job, downstream_job;
```

Expected transitions are:

```text
adf_ingestion -> databricks_bronze = COMPLETED
databricks_bronze -> databricks_silver = READY
```

## 7. Idempotency, failure, drift, and backfill tests

Run these tests with synthetic fixtures only:

1. Rerun the same successful batch; all tables must be
   `SKIPPED_ALREADY_SUCCEEDED` and target counts must not increase.
2. Submit a nullable additive-column fixture; it must be accepted and recorded as allowed
   additive drift.
3. Submit a missing-required-column or incompatible-type fixture under a new batch; the
   table must fail, record the error, and must not publish Silver readiness.
4. Submit a corrupt JSON/CSV fixture if those formats are enabled; malformed rows must go
   to quarantine and counts must reconcile.
5. Run a Phase 3 bounded backfill with a new batch ID; Bronze must process it independently
   without changing an earlier batch partition.
6. Force a retryable failure after registry start; the retry must replace only that batch
   partition and produce no duplicates.

## 8. Teardown

After all later-phase end-to-end tests finish, destroy Azure resources with the approved
Terraform destroy workflow. Confirm job clusters are terminated before teardown and
retain only sanitized evidence required for the portfolio demonstration.

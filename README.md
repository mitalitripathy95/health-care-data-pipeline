# Healthcare Data Platform

A cloud-first portfolio demonstration of a synthetic healthcare claims and clinical data platform built on Azure, Databricks/Spark, ADLS Gen2, and Snowflake.

> This project uses synthetic data and demonstrates HIPAA-aligned technical controls. It is not a claim of HIPAA compliance.

## Current status

**Phases 0–4 are complete as code and static validation only.** Phase 1 provides source schemas,
contracts, deterministic synthetic data generation, validation, and mutation fixtures.
Phase 2 provides the Terraform infrastructure. Phase 3 provides metadata-driven ADF
ingestion, Key Vault-backed linked services, parameterized datasets, immutable Bronze
landing, composite watermarks, audit/locking procedures, and metadata for all 19 source
tables. Phase 4 provides the manifest-gated Databricks Bronze wheel and Asset Bundle,
explicit contracts for all 19 tables, controlled schema drift, corrupt-row quarantine,
Delta audit/registry tables, and deterministic retry/backfill behavior on trial-safe
ephemeral compute.

No Azure resources have been deployed. Azure/Databricks deployment, Unity Catalog
acceptance, and Spark/Delta runtime testing remain deferred until all project phases are
implemented. See [`PROJECT_PLAN.md`](PROJECT_PLAN.md), the
[Phase 3 architecture](docs/architecture/phase-3-adf-ingestion.md),
[Phase 3 deployment/test runbook](docs/runbooks/phase-3-adf-ingestion.md),
[Phase 4 architecture](docs/architecture/phase-4-databricks-bronze.md), and
[Phase 4 deployment/test runbook](docs/runbooks/phase-4-databricks-bronze.md).

## Local quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
make check
make preflight
make cost-preflight
```

Local Python and Terraform commands are for static validation only. The actual generator,
databases, ingestion, Spark transformations, and serving workloads will run in Azure.
Cloud deployment is intentionally blocked until all application and infrastructure code is
prepared, reviewed, and account-specific values are supplied securely.

## Phase 1 local synthetic data

The generator models two source systems:

- PostgreSQL `clinical`: patients, providers, facilities, encounters, and clinical events.
- Azure SQL `payer`: members, plans, enrollment, claims, authorizations, payments, and
  adjustments. Azure SQL also owns the later pipeline-control schema.

Profiles are deterministic and restartable. `tiny` is the default trial-safe profile;
`small` and `medium` are available for local performance testing. The profile counts are
defined in `src/synthetic_data/config/profiles.json` (the YAML files are human-readable
references).

```bash
.venv311/bin/python -m synthetic_data.cli generate \
  --profile tiny --seed 20260905 --batch-id initial
.venv311/bin/python -m synthetic_data.cli validate --batch-id initial
.venv311/bin/python -m synthetic_data.cli load --target all --batch-id initial
```

Generated JSONL files and a checksum/row-count manifest are written to
`data/generated/<batch_id>/`. The local loader verifies the manifest; PostgreSQL and
Azure SQL connectivity adapters are intentionally deferred to a later phase.

Mutation fixtures exercise quality and incremental processing:

```bash
.venv311/bin/python -m synthetic_data.cli mutate \
  --scenario broken_foreign_key --source-batch initial --batch-id bad-fk
.venv311/bin/python -m synthetic_data.cli validate --batch-id bad-fk

.venv311/bin/python -m synthetic_data.cli mutate \
  --scenario incremental_01 --source-batch initial --batch-id inc-001
```

Incremental extraction uses a composite watermark: PostgreSQL
`(updated_at, primary_key)` and Azure SQL `(modified_at, primary_key)`. This handles
multiple records sharing an identical timestamp.

## Safety rules

- Never commit `.env`, credentials, keys, tokens, or real healthcare data.
- Use only synthetic data.
- Use `terraform plan` before every apply and `terraform destroy` after the demonstration.
- Keep Azure and Snowflake compute suspended when not actively testing.

Phase 0 operational runbooks are in `docs/runbooks/`, `docs/cost/`, and
`docs/security/`. Cloud login and deployment are intentionally deferred until
the missing CLI tools are installed and the trial subscription is confirmed.

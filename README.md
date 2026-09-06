# Healthcare Data Platform

A cloud-first portfolio demonstration of a synthetic healthcare claims and clinical data platform built on Azure, Databricks/Spark, ADLS Gen2, and Snowflake.

> This project uses synthetic data and demonstrates HIPAA-aligned technical controls. It is not a claim of HIPAA compliance.

## Current status

Phase 0 (repository and workstation foundation) is complete. Phase 1 source schemas,
contracts, deterministic synthetic data generation, validation, mutation fixtures, and
local loader verification are implemented. No cloud resources are deployed by this
repository yet. Read [`PROJECT_PLAN.md`](PROJECT_PLAN.md) and the Phase 1 runbook before
implementation of the cloud layers.

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

If a cloud CLI is unavailable, local Python tests and Phase 1 generation can still run.
Cloud deployment is intentionally blocked until all application and infrastructure code
is prepared, reviewed, and account-specific values are supplied securely.

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

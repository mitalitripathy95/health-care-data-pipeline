# Runbook — Phase 1 synthetic source data

## Prerequisites

From the repository root:

```bash
source .venv311/bin/activate
```

## Generate and validate an initial batch

```bash
rm -rf data/generated/initial
.venv311/bin/python -m synthetic_data.cli generate \
  --profile tiny --seed 20260905 --batch-id initial
.venv311/bin/python -m synthetic_data.cli validate --batch-id initial
.venv311/bin/python -m synthetic_data.cli load --target all --batch-id initial
```

Validation returns JSON with `passed: true` for a valid batch. The local load command
does not contact a database; it verifies the manifest and reports table counts.

## Create quality fixtures

```bash
.venv311/bin/python -m synthetic_data.cli mutate \
  --scenario broken_foreign_key --source-batch initial --batch-id bad-fk
.venv311/bin/python -m synthetic_data.cli validate --batch-id bad-fk

.venv311/bin/python -m synthetic_data.cli mutate \
  --scenario invalid_financial --source-batch initial --batch-id bad-financial
.venv311/bin/python -m synthetic_data.cli validate --batch-id bad-financial
```

These validations should fail and return non-empty error collections. This is expected;
the fixtures are used to test DQ gates.

## Create incremental fixtures

```bash
.venv311/bin/python -m synthetic_data.cli mutate \
  --scenario incremental_01 --source-batch initial --batch-id inc-001
.venv311/bin/python -m synthetic_data.cli mutate \
  --scenario incremental_02 --source-batch initial --batch-id inc-002
```

The two claims changed by each fixture intentionally share a timestamp. Use the
composite watermark helpers in `src/synthetic_data/watermark.py`, never a timestamp-only
predicate.

## Output and safety

- Do not commit generated batches; `data/generated/` is ignored.
- Use only synthetic values and `.invalid` email domains.
- Keep the tiny profile for Azure trial demonstrations unless a cost review approves a
  larger run.
- Database adapters currently fail closed with `NotImplementedError`; database loading
  is a later phase after infrastructure and secret handling are implemented.

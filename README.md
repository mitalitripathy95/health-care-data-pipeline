# Healthcare Data Platform

A cloud-first portfolio demonstration of a synthetic healthcare claims and clinical data platform built on Azure, Databricks/Spark, ADLS Gen2, and Snowflake.

> This project uses synthetic data and demonstrates HIPAA-aligned technical controls. It is not a claim of HIPAA compliance.

## Current status

Phase 0 (repository and workstation foundation) is in progress. No cloud resources are deployed by this repository yet. Read [`PROJECT_PLAN.md`](PROJECT_PLAN.md) before implementation.

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

If a cloud CLI is unavailable, local Python tests can still run. Cloud deployment is intentionally blocked until the Phase 0 preflight passes and account-specific values are supplied securely.

## Safety rules

- Never commit `.env`, credentials, keys, tokens, or real healthcare data.
- Use only synthetic data.
- Use `terraform plan` before every apply and `terraform destroy` after the demonstration.
- Keep Azure and Snowflake compute suspended when not actively testing.

Phase 0 operational runbooks are in `docs/runbooks/`, `docs/cost/`, and
`docs/security/`. Cloud login and deployment are intentionally deferred until
the missing CLI tools are installed and the trial subscription is confirmed.

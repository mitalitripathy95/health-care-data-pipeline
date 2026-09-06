"""Lightweight distribution checks for synthetic source data."""

from __future__ import annotations

from pathlib import Path


def _has_rows(batch: Path, domain: str, table: str) -> bool:
    path = batch / domain / f"{table}.jsonl"
    if not path.exists():
        return False
    with path.open(encoding="utf-8") as handle:
        return any(line.strip() for line in handle)


def validate_distribution(root: str | Path, batch_id: str) -> list[str]:
    """Return errors for empty required driving tables in a generated batch."""
    errors = []
    batch = Path(root) / batch_id
    for domain, table in (("clinical_provider", "patients"), ("member_claims", "claims")):
        if not _has_rows(batch, domain, table):
            errors.append(f"{domain}.{table} must contain at least one row")
    return errors


__all__ = ["validate_distribution"]

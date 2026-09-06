from __future__ import annotations

import hashlib
import json
from pathlib import Path
from shutil import copytree


def mutate(root: str | Path, source_batch: str, scenario: str, batch_id: str):
    src = Path(root) / source_batch
    dst = Path(root) / batch_id
    if dst.exists():
        raise FileExistsError(dst)
    copytree(src, dst)
    if scenario in ("quality_failures", "broken_foreign_key", "invalid_financial"):
        if scenario == "broken_foreign_key":
            p = dst / "member_claims" / "claims.jsonl"
            rows = [json.loads(x) for x in p.read_text().splitlines()]
            rows[0]["member_id"] = -1
            p.write_text(
                "\n".join(json.dumps(x, sort_keys=True, separators=(",", ":")) for x in rows) + "\n"
            )
        else:
            p = dst / "member_claims" / "claims.jsonl"
            rows = [json.loads(x) for x in p.read_text().splitlines()]
            rows[0]["paid_amount"] = rows[0]["billed_amount"] + 1
            p.write_text(
                "\n".join(json.dumps(x, sort_keys=True, separators=(",", ":")) for x in rows) + "\n"
            )
    elif scenario == "duplicate_event":
        p = dst / "member_claims" / "claims.jsonl"
        lines = p.read_text().splitlines()
        p.write_text("\n".join([lines[0], lines[0], *lines[1:]]) + "\n")
    elif scenario in ("incremental_01", "incremental_02"):
        p = dst / "member_claims" / "claims.jsonl"
        rows = [json.loads(x) for x in p.read_text().splitlines()]
        # Two changed rows intentionally share the timestamp. Consumers must use
        # (modified_at, claim_id), not modified_at alone, to avoid skipped rows.
        timestamp = (
            "2025-02-01T00:00:00+00:00"
            if scenario == "incremental_01"
            else "2025-03-01T00:00:00+00:00"
        )
        rows[0]["modified_at"] = timestamp
        rows[1]["modified_at"] = timestamp
        p.write_text(
            "\n".join(json.dumps(x, sort_keys=True, separators=(",", ":")) for x in rows) + "\n"
        )
    else:
        raise ValueError(f"unknown scenario: {scenario}")
    _refresh_manifest(dst)
    return dst


def _refresh_manifest(batch: Path) -> None:
    """Refresh checksums/counts after a deliberate scenario mutation."""
    manifest_path = batch / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for _table_name, metadata in manifest["table_metadata"].items():
        path = batch / metadata["path"]
        content = path.read_bytes()
        metadata["sha256"] = hashlib.sha256(content).hexdigest()
        metadata["row_count"] = len(content.decode("utf-8").splitlines())
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

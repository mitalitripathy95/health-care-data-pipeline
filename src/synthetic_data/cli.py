from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .generator import generate
from .loaders.local import LocalFileLoader
from .scenarios.mutate import mutate
from .validation.checks import validate_batch


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    base = Path(os.getenv("SYNTHETIC_OUTPUT_DIR", "data/generated"))
    g = sub.add_parser("generate")
    g.add_argument("--profile", default="tiny")
    g.add_argument("--seed", type=int, default=20260905)
    g.add_argument("--batch-id", default="initial")
    g.add_argument("--output-dir", default=str(base))
    m = sub.add_parser("mutate")
    m.add_argument("--scenario", required=True)
    m.add_argument("--batch-id", required=True)
    m.add_argument("--source-batch", default="initial")
    m.add_argument("--output-dir", default=str(base))
    v = sub.add_parser("validate")
    v.add_argument("--batch-id", required=True)
    v.add_argument("--output-dir", default=str(base))
    load_parser = sub.add_parser("load")
    load_parser.add_argument("--target", default="all")
    load_parser.add_argument("--batch-id", required=True)
    load_parser.add_argument("--output-dir", default=str(base))
    a = p.parse_args()
    if a.command == "generate":
        result = generate(a.profile, a.seed, a.batch_id, a.output_dir)
    elif a.command == "mutate":
        result = {
            "batch_id": a.batch_id,
            "path": str(mutate(a.output_dir, a.source_batch, a.scenario, a.batch_id)),
        }
    elif a.command == "validate":
        result = validate_batch(a.output_dir, a.batch_id)
    else:
        batch_path = Path(a.output_dir) / a.batch_id
        selected = None if a.target == "all" else [a.target]
        counts = LocalFileLoader().load_batch(batch_path, selected)
        result = {
            "batch_id": a.batch_id,
            "status": "local_load_verified",
            "target": a.target,
            "tables": counts,
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not (a.command == "validate" and not result["passed"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Offline loader that verifies a generated batch without database credentials."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path


class LocalFileLoader:
    def load_batch(self, batch_path: Path, tables: Sequence[str] | None = None) -> dict[str, int]:
        manifest = json.loads((Path(batch_path) / "manifest.json").read_text(encoding="utf-8"))
        selected = set(tables or manifest["tables"])
        return {
            name: metadata["row_count"]
            for name, metadata in manifest["table_metadata"].items()
            if name.split(".")[-1] in selected
        }

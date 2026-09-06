"""Azure SQL adapter boundary for generated JSONL source batches."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


class AzureSqlLoader:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    def load_batch(self, batch_path: Path, tables: Sequence[str] | None = None) -> dict[str, int]:
        try:
            import pyodbc  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Install the optional azure-sql extra (pyodbc) to load Azure SQL"
            ) from exc
        del pyodbc
        raise NotImplementedError("Database loading is enabled in the Phase 2 connectivity slice")

"""Load adapter contracts; adapters are intentionally optional in Phase 1."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol


class SourceLoader(Protocol):
    def load_batch(
        self, batch_path: Path, tables: Sequence[str] | None = None
    ) -> dict[str, int]: ...

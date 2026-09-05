"""Safe configuration helpers; secrets are supplied through environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    """Non-secret runtime configuration used by local tooling and cloud jobs."""

    environment: str
    azure_location: str
    batch_profile: str

    @classmethod
    def from_environment(cls) -> RuntimeConfig:
        return cls(
            environment=os.getenv("PIPELINE_ENV", "local"),
            azure_location=os.getenv("AZURE_LOCATION", "eastus"),
            batch_profile=os.getenv("DATA_PROFILE", "tiny"),
        )

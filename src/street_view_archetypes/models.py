from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class BoundaryRecord:
    boundary_id: str
    boundary_name: str
    boundary_type: str
    path: Path | None = None


@dataclass(slots=True)
class RunArtifacts:
    boundary_summary: dict[str, Any]
    sample_records: list[dict[str, Any]]
    classified_records: list[dict[str, Any]]
    category_summaries: dict[str, dict[str, Any]]

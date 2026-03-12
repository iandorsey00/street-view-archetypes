from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def write_csv(path: str | Path, records: list[dict[str, Any]]) -> None:
    pd.DataFrame(records).to_csv(path, index=False)


def write_text(path: str | Path, content: str) -> None:
    Path(path).write_text(content, encoding="utf-8")

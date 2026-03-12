from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def summarize_categories(classified_records: list[dict], target_categories: list[str]) -> dict[str, dict]:
    summaries: dict[str, dict] = {}
    for category in target_categories:
        category_records = [
            record for record in classified_records if category in record.get("assigned_categories", [])
        ]
        summaries[category] = _summarize_category(category_records)
    return summaries


def _summarize_category(records: list[dict]) -> dict:
    summary = {
        "sample_count": len(records),
        "reference_count": len(records),
        "strata_counts": _count_values(records, "stratum"),
        "representative_image_path": None,
        "descriptor_centroid": None,
        "notes": [],
    }
    descriptor_rows = []
    descriptor_records = []
    for record in records:
        image_path = record.get("image_path")
        if image_path and Path(image_path).exists():
            descriptor = _image_descriptor(Path(image_path))
            descriptor_rows.append(descriptor)
            descriptor_records.append((record, descriptor))

    if descriptor_rows:
        matrix = np.array(descriptor_rows)
        centroid = matrix.mean(axis=0)
        summary["descriptor_centroid"] = centroid.round(4).tolist()
        representative = min(
            descriptor_records,
            key=lambda pair: float(np.linalg.norm(pair[1] - centroid)),
        )[0]
        summary["representative_image_path"] = representative.get("image_path")
    else:
        summary["notes"].append(
            "No local imagery was available for descriptor analysis; summary is metadata-only."
        )

    return summary


def _image_descriptor(path: Path) -> np.ndarray:
    image = Image.open(path).convert("RGB").resize((128, 128))
    array = np.asarray(image, dtype=np.float32) / 255.0
    mean_rgb = array.mean(axis=(0, 1))
    std_rgb = array.std(axis=(0, 1))
    grayscale = array.mean(axis=2)
    brightness = np.array([grayscale.mean(), grayscale.std()], dtype=np.float32)
    return np.concatenate([mean_rgb, std_rgb, brightness])


def _count_values(records: list[dict], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(field, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return counts

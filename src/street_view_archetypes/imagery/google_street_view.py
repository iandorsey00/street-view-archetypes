from __future__ import annotations

from pathlib import Path

import pandas as pd

from street_view_archetypes.config import ImageryConfig


def build_reference_manifest(sample_records: list[dict], imagery_config: ImageryConfig) -> list[dict]:
    manifest = []
    for record in sample_records:
        reference = {
            **record,
            "provider": imagery_config.provider,
            "mode": imagery_config.mode,
            "image_width": imagery_config.image_width,
            "image_height": imagery_config.image_height,
            "field_of_view": imagery_config.field_of_view,
            "pitch": imagery_config.pitch,
            "reference_url": _build_street_view_reference_url(record, imagery_config),
            "image_path": None,
            "source_labels": [],
        }
        manifest.append(reference)
    return manifest


def merge_local_manifest(reference_manifest: list[dict], local_manifest_path: Path) -> list[dict]:
    manifest_df = pd.DataFrame(reference_manifest)
    local_df = pd.read_csv(local_manifest_path)
    if "sample_id" not in local_df.columns:
        raise ValueError("Local image manifest must include a 'sample_id' column.")
    merged = manifest_df.merge(local_df, on="sample_id", how="left", suffixes=("", "_local"))
    merged["image_path"] = merged.get("image_path_local", merged.get("image_path"))
    merged["source_labels"] = merged.apply(_normalize_labels, axis=1)
    drop_columns = [column for column in merged.columns if column.endswith("_local")]
    return merged.drop(columns=drop_columns).to_dict(orient="records")


def _build_street_view_reference_url(record: dict, imagery_config: ImageryConfig) -> str:
    return (
        "https://maps.googleapis.com/maps/api/streetview"
        f"?size={imagery_config.image_width}x{imagery_config.image_height}"
        f"&location={record['latitude']},{record['longitude']}"
        f"&heading={record['heading']}"
        f"&fov={imagery_config.field_of_view}"
        f"&pitch={imagery_config.pitch}"
    )


def _normalize_labels(row: pd.Series) -> list[str]:
    raw = row.get("source_labels")
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        return [token.strip() for token in raw.split("|") if token.strip()]
    return []

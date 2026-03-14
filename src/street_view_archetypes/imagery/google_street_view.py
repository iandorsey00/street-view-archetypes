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
            "reviewed_categories": "",
            "review_status": "unreviewed",
            "review_notes": "",
        }
        manifest.append(reference)
    return manifest


def merge_local_manifest(reference_manifest: list[dict], local_manifest_path: Path) -> list[dict]:
    manifest_df = pd.DataFrame(reference_manifest)
    local_df = pd.read_csv(local_manifest_path)
    if "sample_id" not in local_df.columns:
        raise ValueError("Local image manifest must include a 'sample_id' column.")
    merge_keys = ["sample_id"]
    if "heading" in manifest_df.columns and "heading" in local_df.columns:
        merge_keys.append("heading")
    merged = manifest_df.merge(local_df, on=merge_keys, how="left", suffixes=("", "_local"))
    merged["image_path"] = merged.get("image_path_local", merged.get("image_path"))
    merged["source_labels"] = merged.apply(_normalize_labels, axis=1)
    merged["reviewed_categories"] = merged.apply(_normalize_reviewed_categories, axis=1)
    merged["review_status"] = merged.apply(_normalize_review_status, axis=1)
    if "review_notes_local" in merged.columns:
        merged["review_notes"] = merged["review_notes_local"].fillna("")
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


def _normalize_reviewed_categories(row: pd.Series) -> list[str]:
    raw = row.get("reviewed_categories_local", row.get("reviewed_categories"))
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        normalized = raw.strip()
        if normalized in {"", "[]", "[ ]", "null", "None"}:
            return []
        return [token.strip() for token in raw.split("|") if token.strip()]
    return []


def _normalize_review_status(row: pd.Series) -> str:
    raw = row.get("review_status_local", row.get("review_status"))
    normalized = str(raw).strip().lower()
    if normalized in {"reviewed", "unreviewed"}:
        return normalized
    categories = _normalize_reviewed_categories(row)
    return "reviewed" if categories else "unreviewed"

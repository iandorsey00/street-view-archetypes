from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from street_view_archetypes.config import AnalysisConfig


def summarize_categories(
    classified_records: list[dict],
    target_categories: list[str],
    analysis_config: AnalysisConfig,
    output_dir: Path,
) -> dict[str, dict]:
    summaries: dict[str, dict] = {}
    for category in target_categories:
        category_records = [
            record for record in classified_records if category in record.get("assigned_categories", [])
        ]
        summaries[category] = _summarize_category(
            category=category,
            records=category_records,
            analysis_config=analysis_config,
            output_dir=output_dir,
        )
    return summaries


def _summarize_category(
    category: str,
    records: list[dict],
    analysis_config: AnalysisConfig,
    output_dir: Path,
) -> dict:
    summary = {
        "sample_count": len(records),
        "reference_count": len(records),
        "strata_counts": _count_values(records, "stratum"),
        "representative_image_path": None,
        "representative_image_set": [],
        "representative_contact_sheet_path": None,
        "feature_centroid": None,
        "feature_dimension": None,
        "within_category_dispersion": None,
        "composite_image_path": None,
        "notes": [],
    }
    feature_rows = []
    feature_records = []
    for record in records:
        image_path = record.get("image_path")
        if image_path and Path(image_path).exists():
            descriptor = _extract_features(Path(image_path), analysis_config.feature_extractor)
            feature_rows.append(descriptor)
            feature_records.append((record, descriptor))

    if feature_rows:
        matrix = np.array(feature_rows)
        centroid = matrix.mean(axis=0)
        distances = np.linalg.norm(matrix - centroid, axis=1)
        summary["feature_centroid"] = centroid.round(4).tolist()
        summary["feature_dimension"] = int(matrix.shape[1])
        summary["within_category_dispersion"] = round(
            float(np.mean(distances)),
            5,
        )
        ranked_records = sorted(
            (
                {
                    "image_path": pair[0].get("image_path"),
                    "sample_id": pair[0].get("sample_id"),
                    "heading": pair[0].get("heading"),
                    "distance_to_centroid": round(float(distance), 6),
                }
                for pair, distance in zip(feature_records, distances)
            ),
            key=lambda row: row["distance_to_centroid"],
        )
        summary["representative_image_set"] = ranked_records[: analysis_config.representative_set_size]
        representative = ranked_records[0]
        summary["representative_image_path"] = representative.get("image_path")
        contact_sheet_path = _write_contact_sheet(
            category=category,
            representative_set=summary["representative_image_set"],
            output_dir=output_dir,
        )
        summary["representative_contact_sheet_path"] = str(contact_sheet_path) if contact_sheet_path else None
        if analysis_config.generate_composite:
            composite_path = _write_composite_image(
                category=category,
                records=records,
                output_dir=output_dir,
                composite_size=analysis_config.composite_size,
            )
            summary["composite_image_path"] = str(composite_path) if composite_path else None
            if composite_path:
                summary["notes"].append(
                    "Composite image is illustrative only and should not be treated as the primary archetype."
                )
    else:
        summary["notes"].append(
            "No local imagery was available for feature analysis; summary is metadata-only."
        )

    return summary


def _extract_features(path: Path, extractor_name: str) -> np.ndarray:
    if extractor_name != "pooled_descriptor_v1":
        raise ValueError(f"Unsupported feature extractor: {extractor_name}")

    image = Image.open(path).convert("RGB").resize((128, 128))
    array = np.asarray(image, dtype=np.float32) / 255.0

    pooled_rgb = _pool_channels(array, bins=4)
    mean_rgb = array.mean(axis=(0, 1))
    std_rgb = array.std(axis=(0, 1))
    rgb_histograms = np.concatenate(
        [np.histogram(array[:, :, channel], bins=8, range=(0.0, 1.0), density=True)[0] for channel in range(3)]
    )

    grayscale = array.mean(axis=2)
    brightness = np.array([grayscale.mean(), grayscale.std()], dtype=np.float32)
    gray_histogram = np.histogram(grayscale, bins=8, range=(0.0, 1.0), density=True)[0]

    edge_strength = _edge_strength(grayscale)
    pooled_edges = _pool_single_channel(edge_strength, bins=4)
    edge_stats = np.array([edge_strength.mean(), edge_strength.std()], dtype=np.float32)

    return np.concatenate(
        [
            pooled_rgb,
            mean_rgb,
            std_rgb,
            rgb_histograms.astype(np.float32),
            gray_histogram.astype(np.float32),
            pooled_edges,
            edge_stats,
            brightness,
        ]
    )


def _write_composite_image(
    category: str,
    records: list[dict],
    output_dir: Path,
    composite_size: int,
) -> Path | None:
    image_arrays = []
    for record in records:
        image_path = record.get("image_path")
        if image_path and Path(image_path).exists():
            image = Image.open(image_path).convert("RGB").resize((composite_size, composite_size))
            image_arrays.append(np.asarray(image, dtype=np.float32))

    if not image_arrays:
        return None

    composite_array = np.mean(np.stack(image_arrays, axis=0), axis=0).clip(0, 255).astype(np.uint8)
    composite_dir = output_dir / "archetypes"
    composite_dir.mkdir(parents=True, exist_ok=True)
    composite_path = composite_dir / f"{category}_composite.png"
    Image.fromarray(composite_array).save(composite_path)
    return composite_path


def _write_contact_sheet(
    category: str,
    representative_set: list[dict],
    output_dir: Path,
    cell_size: int = 220,
    padding: int = 12,
) -> Path | None:
    image_paths = [Path(row["image_path"]) for row in representative_set if row.get("image_path")]
    image_paths = [path for path in image_paths if path.exists()]
    if not image_paths:
        return None

    count = len(image_paths)
    columns = min(3, count)
    rows = int(np.ceil(count / columns))
    width = columns * cell_size + (columns + 1) * padding
    height = rows * cell_size + (rows + 1) * padding

    canvas = Image.new("RGB", (width, height), color=(245, 240, 232))
    for index, path in enumerate(image_paths):
        image = Image.open(path).convert("RGB")
        image.thumbnail((cell_size, cell_size))
        row = index // columns
        col = index % columns
        x = padding + col * (cell_size + padding) + (cell_size - image.width) // 2
        y = padding + row * (cell_size + padding) + (cell_size - image.height) // 2
        canvas.paste(image, (x, y))

    archetype_dir = output_dir / "archetypes"
    archetype_dir.mkdir(parents=True, exist_ok=True)
    contact_sheet_path = archetype_dir / f"{category}_representative_set.png"
    canvas.save(contact_sheet_path)
    return contact_sheet_path


def _pool_channels(array: np.ndarray, bins: int) -> np.ndarray:
    height, width, channels = array.shape
    pooled = []
    row_edges = np.linspace(0, height, bins + 1, dtype=int)
    col_edges = np.linspace(0, width, bins + 1, dtype=int)
    for row_index in range(bins):
        for col_index in range(bins):
            patch = array[row_edges[row_index] : row_edges[row_index + 1], col_edges[col_index] : col_edges[col_index + 1], :]
            pooled.append(patch.mean(axis=(0, 1)))
    return np.concatenate(pooled).astype(np.float32)


def _pool_single_channel(array: np.ndarray, bins: int) -> np.ndarray:
    height, width = array.shape
    pooled = []
    row_edges = np.linspace(0, height, bins + 1, dtype=int)
    col_edges = np.linspace(0, width, bins + 1, dtype=int)
    for row_index in range(bins):
        for col_index in range(bins):
            patch = array[row_edges[row_index] : row_edges[row_index + 1], col_edges[col_index] : col_edges[col_index + 1]]
            pooled.append(np.array([patch.mean()], dtype=np.float32))
    return np.concatenate(pooled).astype(np.float32)


def _edge_strength(grayscale: np.ndarray) -> np.ndarray:
    grad_x = np.diff(grayscale, axis=1, append=grayscale[:, -1:])
    grad_y = np.diff(grayscale, axis=0, append=grayscale[-1:, :])
    return np.sqrt((grad_x ** 2) + (grad_y ** 2)).astype(np.float32)


def _count_values(records: list[dict], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(field, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return counts

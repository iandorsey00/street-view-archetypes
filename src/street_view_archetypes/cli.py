from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from street_view_archetypes.config import load_pipeline_config
from street_view_archetypes.pipeline import build_manifest, run_pipeline
from street_view_archetypes.utils.io import ensure_dir, write_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Street View Archetypes CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    show_config = subparsers.add_parser("show-config", help="Load and print a pipeline config")
    show_config.add_argument("config_path")

    prepare_manifest = subparsers.add_parser(
        "prepare-manifest",
        help="Generate a review manifest CSV from a pipeline config",
    )
    prepare_manifest.add_argument("config_path")
    prepare_manifest.add_argument("output_csv")

    validate_manifest = subparsers.add_parser(
        "validate-manifest",
        help="Validate a reviewed manifest CSV before running the pipeline",
    )
    validate_manifest.add_argument("manifest_csv")

    run = subparsers.add_parser("run", help="Run the MVP pipeline")
    run.add_argument("config_path")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "show-config":
        config = load_pipeline_config(args.config_path)
        print(json.dumps(config.model_dump(mode="json"), indent=2, default=str))
        return

    if args.command == "prepare-manifest":
        config = load_pipeline_config(args.config_path)
        manifest = build_manifest(config)
        output_path = Path(args.output_csv).resolve()
        ensure_dir(output_path.parent)
        write_csv(output_path, manifest)
        print(
            json.dumps(
                {
                    "run_name": config.run.name,
                    "output_csv": str(output_path),
                    "record_count": len(manifest),
                },
                indent=2,
            )
        )
        return

    if args.command == "validate-manifest":
        validation = validate_manifest_csv(args.manifest_csv)
        print(json.dumps(validation, indent=2))
        return

    if args.command == "run":
        config = load_pipeline_config(args.config_path)
        artifacts = run_pipeline(config)
        print(
            json.dumps(
                {
                    "run_name": config.run.name,
                    "output_dir": str(config.run.output_dir),
                    "boundary": artifacts.boundary_summary,
                    "categories": artifacts.category_summaries,
                },
                indent=2,
            )
        )


def validate_manifest_csv(path: str | Path) -> dict[str, object]:
    manifest_path = Path(path).resolve()
    df = pd.read_csv(manifest_path)

    required_columns = [
        "sample_id",
        "image_path",
        "source_labels",
        "reviewed_categories",
        "review_notes",
    ]
    missing_columns = [column for column in required_columns if column not in df.columns]

    missing_image_rows = []
    invalid_path_rows = []
    reviewed_count = 0

    for index, row in df.iterrows():
        image_path = row.get("image_path")
        reviewed_categories = row.get("reviewed_categories")

        if isinstance(reviewed_categories, str) and reviewed_categories.strip():
            reviewed_count += 1

        if pd.isna(image_path) or not str(image_path).strip():
            missing_image_rows.append(index + 2)
            continue

        candidate = Path(str(image_path).strip())
        if not candidate.is_absolute() or not candidate.exists():
            invalid_path_rows.append(index + 2)

    return {
        "manifest_csv": str(manifest_path),
        "row_count": int(len(df)),
        "required_columns_present": len(missing_columns) == 0,
        "missing_columns": missing_columns,
        "reviewed_row_count": reviewed_count,
        "rows_missing_image_path": missing_image_rows[:25],
        "rows_with_invalid_image_path": invalid_path_rows[:25],
        "valid": len(missing_columns) == 0 and not missing_image_rows and not invalid_path_rows,
    }


if __name__ == "__main__":
    main()

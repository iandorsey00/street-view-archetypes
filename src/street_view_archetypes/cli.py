from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from street_view_archetypes.config import load_pipeline_config
from street_view_archetypes.pipeline import build_manifest, run_pipeline
from street_view_archetypes.review.server import run_review_server
from street_view_archetypes.studies.init import init_study
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

    init_study_parser = subparsers.add_parser(
        "init-study",
        help="Create a local study config, fetch a boundary, and prepare a manifest",
    )
    init_study_parser.add_argument("--place", required=True)
    init_study_parser.add_argument("--boundary-type", choices=["city", "county"], required=True)
    init_study_parser.add_argument("--category", required=True)
    init_study_parser.add_argument("--download-imagery", action="store_true")
    init_study_parser.add_argument("--google-api-key")
    init_study_parser.add_argument("--spacing-meters", type=int, default=400)
    init_study_parser.add_argument("--min-points", type=int, default=24)
    init_study_parser.add_argument("--max-points", type=int, default=120)

    review_manifest = subparsers.add_parser(
        "review-manifest",
        help="Start a local review server for the manifest referenced by a config",
    )
    review_manifest.add_argument("config_path")
    review_manifest.add_argument("--host", default="127.0.0.1")
    review_manifest.add_argument("--port", type=int, default=8765)

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

    if args.command == "init-study":
        try:
            result = init_study(
                place=args.place,
                boundary_type=args.boundary_type,
                category=args.category,
                download_imagery=args.download_imagery,
                imagery_api_key=args.google_api_key,
                spacing_meters=args.spacing_meters,
                min_points=args.min_points,
                max_points=args.max_points,
            )
            print(json.dumps(result, indent=2))
        except KeyboardInterrupt:
            print("Study initialization interrupted. Partial local files may have been created.", file=sys.stderr)
            raise SystemExit(130)
        return

    if args.command == "review-manifest":
        run_review_server(args.config_path, host=args.host, port=args.port)
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

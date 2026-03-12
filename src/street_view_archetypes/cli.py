from __future__ import annotations

import argparse
import json
from pathlib import Path

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


if __name__ == "__main__":
    main()

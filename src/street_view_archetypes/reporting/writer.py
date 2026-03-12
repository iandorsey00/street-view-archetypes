from __future__ import annotations

from pathlib import Path

from street_view_archetypes.config import PipelineConfig
from street_view_archetypes.models import RunArtifacts
from street_view_archetypes.utils.io import ensure_dir, write_csv, write_json, write_text


def write_outputs(config: PipelineConfig, artifacts: RunArtifacts) -> Path:
    output_dir = ensure_dir(config.run.output_dir)

    if config.reporting.write_json:
        write_json(output_dir / "boundary_summary.json", artifacts.boundary_summary)
        write_json(output_dir / "category_summaries.json", artifacts.category_summaries)
    if config.reporting.write_csv:
        write_csv(output_dir / "sample_manifest.csv", artifacts.sample_records)
        write_csv(output_dir / "classified_manifest.csv", artifacts.classified_records)
    if config.reporting.write_markdown:
        write_text(output_dir / "report.md", _render_markdown_report(config, artifacts))
    return output_dir


def _render_markdown_report(config: PipelineConfig, artifacts: RunArtifacts) -> str:
    boundary = artifacts.boundary_summary
    lines = [
        f"# Street View Archetypes Report: {config.run.name}",
        "",
        "## Boundary",
        f"- Boundary name: {boundary['boundary_name']}",
        f"- Boundary type: {boundary['boundary_type']}",
        f"- Boundary id: {boundary['boundary_id']}",
        f"- Area (sq km): {boundary['area_sq_km']}",
        "",
        "## Sampling",
        f"- Sample references: {len(artifacts.sample_records)}",
        f"- Heading mode: {config.sampling.heading_mode}",
        f"- Sampling method: {config.sampling.method}",
        "",
        "## Category Summaries",
    ]

    for category, summary in artifacts.category_summaries.items():
        lines.extend(
            [
                f"### {category}",
                f"- Classified references: {summary['reference_count']}",
                f"- Representative image path: {summary['representative_image_path']}",
                f"- Descriptor centroid available: {'yes' if summary['descriptor_centroid'] else 'no'}",
            ]
        )
        if summary["notes"]:
            for note in summary["notes"]:
                lines.append(f"- Note: {note}")
        lines.append("")

    lines.extend(
        [
            "## Legal and Method Notes",
            "- This MVP emphasizes metadata, manifests, and references for Google Street View workflows.",
            "- Review current Google Maps Platform and Street View terms before downloading, storing, or publishing imagery-derived outputs.",
            "- Category summaries are only as strong as the sampling design and category filter applied.",
        ]
    )
    return "\n".join(lines) + "\n"

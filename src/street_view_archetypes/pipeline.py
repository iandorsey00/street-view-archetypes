from __future__ import annotations

from street_view_archetypes.boundaries.loaders import load_boundary, summarize_boundary
from street_view_archetypes.classification.rules import classify_manifest
from street_view_archetypes.config import PipelineConfig, load_categories
from street_view_archetypes.imagery.google_street_view import (
    build_reference_manifest,
    merge_local_manifest,
)
from street_view_archetypes.models import RunArtifacts
from street_view_archetypes.reporting.writer import write_outputs
from street_view_archetypes.sampling.grid import expand_headings, sample_points
from street_view_archetypes.summarization.archetypes import summarize_categories


def run_pipeline(config: PipelineConfig) -> RunArtifacts:
    boundary_gdf = load_boundary(config.boundary)
    boundary_summary = summarize_boundary(boundary_gdf)

    sampled_points = sample_points(boundary_gdf, config.sampling)
    sample_records = expand_headings(sampled_points, config.sampling.heading_mode)

    manifest = build_reference_manifest(sample_records, config.imagery)
    if config.imagery.mode == "local_images":
        if config.imagery.local_manifest_path is None:
            raise ValueError("local_manifest_path is required when imagery.mode='local_images'.")
        manifest = merge_local_manifest(manifest, config.imagery.local_manifest_path)

    categories = load_categories(config.classification.categories_config)
    classified = classify_manifest(
        manifest,
        categories=categories,
        targets=config.classification.target_categories,
    )
    category_summaries = summarize_categories(classified, config.classification.target_categories)

    artifacts = RunArtifacts(
        boundary_summary=boundary_summary,
        sample_records=manifest,
        classified_records=classified,
        category_summaries=category_summaries,
    )
    write_outputs(config, artifacts)
    return artifacts

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class RunConfig(BaseModel):
    name: str
    output_dir: Path


class BoundaryConfig(BaseModel):
    boundary_type: Literal["city", "county", "zip_code", "census_tract", "metro_area", "state"]
    source: Literal["file", "identifier"]
    path: Path | None = None
    boundary_id: str
    boundary_name: str
    identifier: str | None = None


class SamplingConfig(BaseModel):
    method: Literal["grid"] = "grid"
    spacing_meters: int = Field(default=500, gt=0)
    min_points: int = Field(default=25, gt=0)
    max_points: int = Field(default=100, gt=0)
    heading_mode: Literal["cardinal", "single"] = "cardinal"
    stratify_by: Literal["quadrant", "none"] = "quadrant"


class ImageryConfig(BaseModel):
    provider: Literal["google_street_view"] = "google_street_view"
    mode: Literal["references_only", "local_images"] = "references_only"
    local_manifest_path: Path | None = None
    image_width: int = 640
    image_height: int = 640
    field_of_view: int = 90
    pitch: int = 0


class ClassificationConfig(BaseModel):
    categories_config: Path
    target_categories: list[str]


class AnalysisConfig(BaseModel):
    summary_method: Literal["descriptor_centroid", "feature_centroid"] = "feature_centroid"
    comparison_mode: Literal["within_run", "cross_run"] = "within_run"
    feature_extractor: Literal["pooled_descriptor_v1"] = "pooled_descriptor_v1"
    representative_selection: Literal["centroid_nearest"] = "centroid_nearest"
    generate_composite: bool = False
    composite_size: int = Field(default=256, gt=31, le=1024)


class ReportingConfig(BaseModel):
    write_markdown: bool = True
    write_json: bool = True
    write_csv: bool = True


class PipelineConfig(BaseModel):
    run: RunConfig
    boundary: BoundaryConfig
    sampling: SamplingConfig
    imagery: ImageryConfig
    classification: ClassificationConfig
    analysis: AnalysisConfig
    reporting: ReportingConfig


def load_yaml(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_pipeline_config(path: str | Path) -> PipelineConfig:
    config_path = Path(path)
    raw = load_yaml(config_path)
    config = PipelineConfig.model_validate(raw)
    config.run.output_dir = _resolve_relative_path(config_path, config.run.output_dir)
    if config.boundary.path is not None:
        config.boundary.path = _resolve_relative_path(config_path, config.boundary.path)
    config.classification.categories_config = _resolve_relative_path(
        config_path, config.classification.categories_config
    )
    if config.imagery.local_manifest_path is not None:
        config.imagery.local_manifest_path = _resolve_relative_path(
            config_path, config.imagery.local_manifest_path
        )
    return config


def load_categories(path: str | Path) -> dict[str, dict]:
    raw = load_yaml(path)
    return raw["categories"]


def _resolve_relative_path(config_path: Path, maybe_relative: Path) -> Path:
    if maybe_relative.is_absolute():
        return maybe_relative
    return (config_path.parent / maybe_relative).resolve()

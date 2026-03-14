from __future__ import annotations

import math

import geopandas as gpd
import numpy as np
from shapely.geometry import Point

from street_view_archetypes.config import SamplingConfig


def sample_points(boundary_gdf: gpd.GeoDataFrame, sampling_config: SamplingConfig) -> gpd.GeoDataFrame:
    if boundary_gdf.geometry.isna().all():
        raise ValueError("Boundary geometry is empty. Check the resolved boundary file before sampling.")

    projected = boundary_gdf.to_crs(3857)
    polygon = projected.unary_union
    if polygon.is_empty:
        raise ValueError("Boundary geometry is empty after projection. Sampling cannot continue.")

    minx, miny, maxx, maxy = polygon.bounds
    if not np.isfinite([minx, miny, maxx, maxy]).all():
        raise ValueError("Boundary bounds are not finite. Sampling cannot continue.")

    xs = np.arange(minx, maxx + sampling_config.spacing_meters, sampling_config.spacing_meters)
    ys = np.arange(miny, maxy + sampling_config.spacing_meters, sampling_config.spacing_meters)

    points = []
    for x in xs:
        for y in ys:
            point = Point(float(x), float(y))
            if polygon.contains(point):
                points.append(point)

    if not points:
        centroid = polygon.centroid
        points = [Point(float(centroid.x), float(centroid.y))]

    if len(points) < sampling_config.min_points:
        points = _supplement_with_centroid_ring(polygon, points, sampling_config.min_points)

    if len(points) > sampling_config.max_points:
        step = math.ceil(len(points) / sampling_config.max_points)
        points = points[::step][: sampling_config.max_points]

    samples = gpd.GeoDataFrame({"geometry": points}, crs=3857).to_crs(4326)
    samples["sample_id"] = [f"pt-{index:04d}" for index in range(1, len(samples) + 1)]
    return assign_strata(samples, sampling_config.stratify_by)


def expand_headings(samples: gpd.GeoDataFrame, sampling_config: SamplingConfig) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in samples.itertuples():
        headings = _resolve_headings(row, sampling_config)
        for heading in headings:
            records.append(
                {
                    "sample_id": row.sample_id,
                    "latitude": row.geometry.y,
                    "longitude": row.geometry.x,
                    "heading": heading,
                    "stratum": row.stratum,
                }
            )
    return records


def _resolve_headings(row: object, sampling_config: SamplingConfig) -> list[int]:
    if sampling_config.heading_mode == "cardinal":
        return [0, 90, 180, 270]
    if sampling_config.heading_mode == "single":
        return [0]
    if sampling_config.heading_mode == "custom":
        if not sampling_config.heading_values:
            raise ValueError("sampling.heading_values is required when heading_mode='custom'.")
        return _normalize_heading_values(sampling_config.heading_values)
    if sampling_config.heading_mode in {"road_parallel_both", "road_parallel_single"}:
        bearing = getattr(row, sampling_config.heading_bearing_field, None)
        if bearing is None:
            raise ValueError(
                "Road-parallel heading modes require sampled records to include a "
                f"'{sampling_config.heading_bearing_field}' field."
            )
        primary_heading = int(round(float(bearing))) % 360
        if sampling_config.heading_mode == "road_parallel_single":
            return [primary_heading]
        return _normalize_heading_values([primary_heading, (primary_heading + 180) % 360])
    raise ValueError(f"Unsupported heading mode: {sampling_config.heading_mode}")


def _normalize_heading_values(values: list[int]) -> list[int]:
    normalized: list[int] = []
    seen: set[int] = set()
    for value in values:
        heading = int(value) % 360
        if heading in seen:
            continue
        seen.add(heading)
        normalized.append(heading)
    if not normalized:
        raise ValueError("At least one heading value is required.")
    return normalized


def assign_strata(samples: gpd.GeoDataFrame, stratify_by: str) -> gpd.GeoDataFrame:
    if stratify_by == "none":
        samples["stratum"] = "all"
        return samples
    centroid = samples.unary_union.centroid
    samples["stratum"] = samples.geometry.apply(lambda geom: _quadrant_label(geom.x, geom.y, centroid.x, centroid.y))
    return samples


def _quadrant_label(x: float, y: float, centroid_x: float, centroid_y: float) -> str:
    return f"{'N' if y >= centroid_y else 'S'}{'E' if x >= centroid_x else 'W'}"


def _supplement_with_centroid_ring(polygon, points: list[Point], minimum: int) -> list[Point]:
    centroid = polygon.centroid
    updated = list(points)
    radius = 50.0
    angle = 0.0
    while len(updated) < minimum:
        candidate = Point(
            centroid.x + radius * math.cos(math.radians(angle)),
            centroid.y + radius * math.sin(math.radians(angle)),
        )
        if polygon.contains(candidate):
            updated.append(candidate)
        angle += 35
        radius += 10
        if radius > 1000:
            updated.append(centroid)
    return updated

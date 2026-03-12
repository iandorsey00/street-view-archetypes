from __future__ import annotations

import math

import geopandas as gpd
import numpy as np
from shapely.geometry import Point

from street_view_archetypes.config import SamplingConfig


def sample_points(boundary_gdf: gpd.GeoDataFrame, sampling_config: SamplingConfig) -> gpd.GeoDataFrame:
    projected = boundary_gdf.to_crs(3857)
    polygon = projected.unary_union
    minx, miny, maxx, maxy = polygon.bounds

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
    centroid = samples.unary_union.centroid
    samples["stratum"] = samples.geometry.apply(lambda geom: _quadrant_label(geom.x, geom.y, centroid.x, centroid.y))
    return samples


def expand_headings(samples: gpd.GeoDataFrame, heading_mode: str) -> list[dict[str, object]]:
    headings = [0, 90, 180, 270] if heading_mode == "cardinal" else [0]
    records: list[dict[str, object]] = []
    for row in samples.itertuples():
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

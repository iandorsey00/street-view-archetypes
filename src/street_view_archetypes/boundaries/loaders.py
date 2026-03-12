from __future__ import annotations

from pathlib import Path

import geopandas as gpd

from street_view_archetypes.config import BoundaryConfig


def load_boundary(boundary_config: BoundaryConfig) -> gpd.GeoDataFrame:
    if boundary_config.source == "file":
        if boundary_config.path is None:
            raise ValueError("Boundary path is required when source='file'.")
        gdf = gpd.read_file(boundary_config.path)
    else:
        raise NotImplementedError(
            "Identifier-based boundary resolution is planned but not implemented in the MVP."
        )

    if gdf.empty:
        raise ValueError("Boundary file did not contain any features.")

    if "boundary_id" not in gdf.columns:
        gdf["boundary_id"] = boundary_config.boundary_id
    if "boundary_name" not in gdf.columns:
        gdf["boundary_name"] = boundary_config.boundary_name
    if "boundary_type" not in gdf.columns:
        gdf["boundary_type"] = boundary_config.boundary_type

    return gdf.to_crs(4326)


def summarize_boundary(boundary_gdf: gpd.GeoDataFrame) -> dict[str, object]:
    metric = boundary_gdf.to_crs(3857)
    area_sq_km = float(metric.area.sum() / 1_000_000)
    bounds = [float(value) for value in boundary_gdf.total_bounds]
    first = boundary_gdf.iloc[0]
    return {
        "boundary_id": first["boundary_id"],
        "boundary_name": first["boundary_name"],
        "boundary_type": first["boundary_type"],
        "feature_count": int(len(boundary_gdf)),
        "area_sq_km": round(area_sq_km, 3),
        "bounds_wgs84": bounds,
    }

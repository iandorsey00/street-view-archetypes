from __future__ import annotations

import math

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Point

from street_view_archetypes.config import SamplingConfig
from street_view_archetypes.sampling.grid import assign_strata


def sample_road_points(
    boundary_gdf: gpd.GeoDataFrame,
    sampling_config: SamplingConfig,
) -> gpd.GeoDataFrame:
    if sampling_config.network_path is None:
        raise ValueError("sampling.network_path is required when sampling.method='road_network'.")

    roads = gpd.read_file(sampling_config.network_path)
    if roads.empty:
        raise ValueError("Road network file did not contain any features.")

    roads = roads.to_crs(4326)
    boundary = boundary_gdf.to_crs(4326)
    projected_boundary = boundary.to_crs(3857)
    boundary_polygon = projected_boundary.unary_union

    road_lines = _prepare_road_lines(roads)
    if road_lines.empty:
        raise ValueError("Road network file did not contain any line geometries.")

    projected_lines = road_lines.to_crs(3857)
    if sampling_config.clip_to_boundary:
        projected_lines = projected_lines[projected_lines.intersects(boundary_polygon)].copy()
        if projected_lines.empty:
            raise ValueError("Road network does not intersect the study boundary.")
        projected_lines["geometry"] = projected_lines.geometry.intersection(boundary_polygon)
        projected_lines = projected_lines[~projected_lines.geometry.is_empty].copy()

    node_points = _collect_intersection_nodes(projected_lines)
    samples = _sample_along_lines(projected_lines, sampling_config, node_points, boundary_polygon)
    if samples.empty:
        raise ValueError("Road-network sampling produced no usable points. Check spacing and intersection buffer.")

    samples = samples.to_crs(4326)
    samples["sample_id"] = [f"pt-{index:04d}" for index in range(1, len(samples) + 1)]
    samples = assign_strata(samples, sampling_config.stratify_by)
    return samples


def _prepare_road_lines(roads: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    line_geometries = roads[roads.geometry.type.isin(["LineString", "MultiLineString"])].copy()
    if line_geometries.empty:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=roads.crs)
    exploded = line_geometries.explode(index_parts=False).reset_index(drop=True)
    exploded = exploded[exploded.geometry.type == "LineString"].copy()
    return exploded


def _sample_along_lines(
    lines: gpd.GeoDataFrame,
    sampling_config: SamplingConfig,
    node_points: list[Point],
    boundary_polygon,
) -> gpd.GeoDataFrame:
    records: list[dict[str, object]] = []
    half_spacing = sampling_config.spacing_meters / 2.0
    bearing_delta = min(max(sampling_config.spacing_meters / 6.0, 5.0), 25.0)

    for row in lines.itertuples():
        geometry = row.geometry
        if geometry.is_empty or geometry.length == 0:
            continue

        max_distance = geometry.length
        distance = min(half_spacing, max_distance / 2.0)
        while distance < max_distance:
            point = geometry.interpolate(distance)
            if sampling_config.clip_to_boundary and not boundary_polygon.buffer(1e-6).contains(point):
                distance += sampling_config.spacing_meters
                continue
            if sampling_config.intersection_buffer_meters > 0 and _near_any_node(
                point,
                node_points,
                sampling_config.intersection_buffer_meters,
            ):
                distance += sampling_config.spacing_meters
                continue

            records.append(
                {
                    "geometry": point,
                    sampling_config.heading_bearing_field: _segment_bearing(geometry, distance, bearing_delta),
                }
            )
            distance += sampling_config.spacing_meters

    if not records:
        return gpd.GeoDataFrame(
            columns=["geometry", sampling_config.heading_bearing_field],
            geometry="geometry",
            crs=3857,
        )

    samples = gpd.GeoDataFrame(records, geometry="geometry", crs=3857)

    if len(samples) < sampling_config.min_points:
        return samples
    if len(samples) > sampling_config.max_points:
        step = math.ceil(len(samples) / sampling_config.max_points)
        samples = samples.iloc[::step].head(sampling_config.max_points).copy()
    return samples.reset_index(drop=True)


def _collect_intersection_nodes(lines: gpd.GeoDataFrame) -> list[Point]:
    nodes: dict[tuple[int, int], Point] = {}
    for row in lines.itertuples():
        geometry = row.geometry
        if geometry.is_empty:
            continue
        for point in _line_endpoints(geometry):
            _add_node(nodes, point)

    spatial_index = lines.sindex
    for index, geometry in enumerate(lines.geometry):
        for candidate_index in spatial_index.intersection(geometry.bounds):
            if candidate_index <= index:
                continue
            other = lines.geometry.iloc[candidate_index]
            if not geometry.intersects(other):
                continue
            intersection = geometry.intersection(other)
            for point in _extract_points(intersection):
                _add_node(nodes, point)
    return list(nodes.values())


def _line_endpoints(geometry: LineString) -> list[Point]:
    coordinates = list(geometry.coords)
    if len(coordinates) < 2:
        return []
    return [Point(coordinates[0]), Point(coordinates[-1])]


def _extract_points(geometry) -> list[Point]:
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Point":
        return [geometry]
    if geometry.geom_type == "MultiPoint":
        return list(geometry.geoms)
    if geometry.geom_type == "GeometryCollection":
        points: list[Point] = []
        for item in geometry.geoms:
            points.extend(_extract_points(item))
        return points
    return []


def _add_node(nodes: dict[tuple[int, int], Point], point: Point) -> None:
    key = (round(point.x, 1), round(point.y, 1))
    nodes.setdefault(key, point)


def _near_any_node(point: Point, nodes: list[Point], buffer_meters: float) -> bool:
    return any(point.distance(node) < buffer_meters for node in nodes)


def _segment_bearing(line: LineString | MultiLineString, distance: float, delta: float) -> float:
    start_distance = max(0.0, distance - delta)
    end_distance = min(line.length, distance + delta)
    start = line.interpolate(start_distance)
    end = line.interpolate(end_distance)
    dx = end.x - start.x
    dy = end.y - start.y
    angle = math.degrees(math.atan2(dx, dy))
    return (angle + 360.0) % 360.0

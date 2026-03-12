from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml
from shapely.geometry import mapping, shape

from street_view_archetypes.config import load_pipeline_config
from street_view_archetypes.pipeline import build_manifest
from street_view_archetypes.utils.io import ensure_dir, write_csv

TIGER_PLACES = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer"
TIGER_COUNTIES = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer"
PLACES_LAYER_ID = 4
COUNTIES_LAYER_ID = 11

STATE_FIPS = {
    "ALABAMA": "01", "AL": "01", "ALASKA": "02", "AK": "02", "ARIZONA": "04", "AZ": "04",
    "ARKANSAS": "05", "AR": "05", "CALIFORNIA": "06", "CA": "06", "COLORADO": "08", "CO": "08",
    "CONNECTICUT": "09", "CT": "09", "DELAWARE": "10", "DE": "10", "DISTRICT OF COLUMBIA": "11",
    "DC": "11", "FLORIDA": "12", "FL": "12", "GEORGIA": "13", "GA": "13", "HAWAII": "15", "HI": "15",
    "IDAHO": "16", "ID": "16", "ILLINOIS": "17", "IL": "17", "INDIANA": "18", "IN": "18",
    "IOWA": "19", "IA": "19", "KANSAS": "20", "KS": "20", "KENTUCKY": "21", "KY": "21",
    "LOUISIANA": "22", "LA": "22", "MAINE": "23", "ME": "23", "MARYLAND": "24", "MD": "24",
    "MASSACHUSETTS": "25", "MA": "25", "MICHIGAN": "26", "MI": "26", "MINNESOTA": "27", "MN": "27",
    "MISSISSIPPI": "28", "MS": "28", "MISSOURI": "29", "MO": "29", "MONTANA": "30", "MT": "30",
    "NEBRASKA": "31", "NE": "31", "NEVADA": "32", "NV": "32", "NEW HAMPSHIRE": "33", "NH": "33",
    "NEW JERSEY": "34", "NJ": "34", "NEW MEXICO": "35", "NM": "35", "NEW YORK": "36", "NY": "36",
    "NORTH CAROLINA": "37", "NC": "37", "NORTH DAKOTA": "38", "ND": "38", "OHIO": "39", "OH": "39",
    "OKLAHOMA": "40", "OK": "40", "OREGON": "41", "OR": "41", "PENNSYLVANIA": "42", "PA": "42",
    "RHODE ISLAND": "44", "RI": "44", "SOUTH CAROLINA": "45", "SC": "45", "SOUTH DAKOTA": "46",
    "SD": "46", "TENNESSEE": "47", "TN": "47", "TEXAS": "48", "TX": "48", "UTAH": "49", "UT": "49",
    "VERMONT": "50", "VT": "50", "VIRGINIA": "51", "VA": "51", "WASHINGTON": "53", "WA": "53",
    "WEST VIRGINIA": "54", "WV": "54", "WISCONSIN": "55", "WI": "55", "WYOMING": "56", "WY": "56",
}


def init_study(
    *,
    place: str,
    boundary_type: str,
    category: str,
    download_imagery: bool,
    imagery_api_key: str | None = None,
    spacing_meters: int = 400,
    min_points: int = 24,
    max_points: int = 120,
) -> dict[str, Any]:
    place_name, state_name = _parse_place(place)
    slug = _slugify(f"{place_name}-{boundary_type}-{category}")
    state_fips = _state_fips(state_name)
    reporter = ProgressReporter()

    reporter.step("Preparing local study folders")
    config_dir = ensure_dir("configs/local")
    boundary_dir = ensure_dir("data/local/boundaries")
    manifest_dir = ensure_dir("data/local/manifests")
    image_dir = ensure_dir(Path("data/local/images") / slug)

    boundary_path = (boundary_dir / f"{slug}.geojson").resolve()
    manifest_path = (manifest_dir / f"{slug}-reviewed.csv").resolve()
    config_path = (config_dir / f"{slug}.yaml").resolve()

    reporter.step(f"Fetching {boundary_type} boundary from Census TIGERweb")
    boundary_geojson = fetch_boundary_geojson(
        place_name=place_name,
        state_fips=state_fips,
        boundary_type=boundary_type,
    )
    boundary_path.write_text(json.dumps(boundary_geojson, indent=2), encoding="utf-8")

    reporter.step("Writing local study config")
    config_payload = _build_local_config_payload(
        place=place,
        boundary_type=boundary_type,
        category=category,
        slug=slug,
        boundary_path=boundary_path,
        manifest_path=manifest_path,
        spacing_meters=spacing_meters,
        min_points=min_points,
        max_points=max_points,
        download_imagery=download_imagery,
    )
    config_path.write_text(yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8")

    reporter.step("Generating sample manifest")
    config = load_pipeline_config(config_path)
    manifest = build_manifest(config)
    if download_imagery:
        api_key = imagery_api_key or os.getenv("GOOGLE_MAPS_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_MAPS_API_KEY is required for --download-imagery.")
        reporter.step("Downloading Street View imagery")
        manifest = download_reference_imagery(
            manifest,
            image_dir=image_dir,
            api_key=api_key,
            reporter=reporter,
            manifest_path=manifest_path,
        )
    reporter.step("Writing reviewed manifest template")
    write_csv(manifest_path, manifest)
    reporter.finish("Study initialization complete")

    return {
        "place": place,
        "boundary_type": boundary_type,
        "category": category,
        "config_path": str(config_path),
        "boundary_path": str(boundary_path),
        "manifest_path": str(manifest_path),
        "downloaded_imagery": download_imagery,
        "manifest_rows": len(manifest),
        "next_command": f"python -m street_view_archetypes.cli run {config_path}",
    }


def fetch_boundary_geojson(*, place_name: str, state_fips: str, boundary_type: str) -> dict[str, Any]:
    if boundary_type == "city":
        service_url = TIGER_PLACES
        layer_id = PLACES_LAYER_ID
        search_text = place_name
    elif boundary_type == "county":
        service_url = TIGER_COUNTIES
        layer_id = COUNTIES_LAYER_ID
        search_text = re.sub(r"\s+County$", "", place_name, flags=re.IGNORECASE)
    else:
        raise ValueError("init-study currently supports boundary_type 'city' and 'county'.")

    match = _find_feature(service_url, layer_id, search_text, state_fips)
    geojson = _query_feature_geojson(service_url, layer_id, match["attributes"])

    for feature in geojson.get("features", []):
        props = feature.setdefault("properties", {})
        props.setdefault("boundary_name", place_name)
        props.setdefault("boundary_type", boundary_type)
        props.setdefault("boundary_id", _extract_geoid(match["attributes"], fallback_name=place_name))
    return geojson


def download_reference_imagery(
    manifest: list[dict[str, Any]],
    *,
    image_dir: Path,
    api_key: str,
    reporter: "ProgressReporter",
    manifest_path: Path,
) -> list[dict[str, Any]]:
    updated_manifest: list[dict[str, Any]] = []
    total = len(manifest)
    for index, record in enumerate(manifest, start=1):
        filename = f"{record['sample_id']}_h{record['heading']}.jpg"
        image_path = image_dir / filename
        temp_path = image_path.with_suffix(".part")
        url = f"{record['reference_url']}&key={urllib.parse.quote(api_key)}"
        try:
            with urllib.request.urlopen(url) as response:
                temp_path.write_bytes(response.read())
            temp_path.replace(image_path)
            updated_manifest.append(
                {
                    **record,
                    "image_path": str(image_path.resolve()),
                    "reviewed_categories": [],
                    "review_notes": "",
                }
            )
            reporter.progress("Downloading imagery", index, total)
        except KeyboardInterrupt:
            if temp_path.exists():
                temp_path.unlink()
            if updated_manifest:
                write_csv(manifest_path, updated_manifest)
            reporter.finish("Interrupted during imagery download; partial manifest saved")
            raise
    return updated_manifest


def _build_local_config_payload(
    *,
    place: str,
    boundary_type: str,
    category: str,
    slug: str,
    boundary_path: Path,
    manifest_path: Path,
    spacing_meters: int,
    min_points: int,
    max_points: int,
    download_imagery: bool,
) -> dict[str, Any]:
    boundary_rel = Path("../../") / boundary_path.relative_to(Path.cwd())
    manifest_rel = Path("../../") / manifest_path.relative_to(Path.cwd())
    return {
        "run": {
            "name": slug,
            "output_dir": f"../../outputs/{slug}",
        },
        "boundary": {
            "boundary_type": boundary_type,
            "source": "file",
            "path": str(boundary_rel),
            "boundary_id": slug,
            "boundary_name": place,
        },
        "sampling": {
            "method": "grid",
            "spacing_meters": spacing_meters,
            "min_points": min_points,
            "max_points": max_points,
            "heading_mode": "cardinal",
            "stratify_by": "quadrant",
        },
        "imagery": {
            "provider": "google_street_view",
            "mode": "local_images" if download_imagery else "references_only",
            "local_manifest_path": str(manifest_rel),
            "image_width": 640,
            "image_height": 640,
            "field_of_view": 90,
            "pitch": 0,
        },
        "classification": {
            "categories_config": "../categories.yaml",
            "target_categories": [category],
        },
        "analysis": {
            "summary_method": "feature_centroid",
            "comparison_mode": "within_run",
            "feature_extractor": "pooled_descriptor_v1",
            "representative_selection": "centroid_nearest",
            "generate_composite": True,
            "composite_size": 256,
        },
        "reporting": {
            "write_markdown": True,
            "write_json": True,
            "write_csv": True,
        },
    }


def _find_feature(service_url: str, layer_id: int, search_text: str, state_fips: str) -> dict[str, Any]:
    where = _build_search_where(layer_id, search_text, state_fips)
    params = urllib.parse.urlencode(
        {
            "where": where,
            "outFields": "*",
            "returnGeometry": "false",
            "f": "pjson",
        }
    )
    payload = _fetch_json(f"{service_url}/{layer_id}/query?{params}")
    candidates = [
        {"attributes": feature.get("attributes", {})}
        for feature in payload.get("features", [])
    ]
    filtered = [
        result
        for result in candidates
        if _match_state(result.get("attributes", {}), state_fips)
        and _match_name(result.get("attributes", {}), search_text)
    ]
    if not filtered:
        filtered = candidates
    if not filtered:
        raise ValueError(f"No boundary match found for '{search_text}' in state {state_fips}.")
    return filtered[0]


def _build_search_where(layer_id: int, search_text: str, state_fips: str) -> str:
    escaped_search = _escape_sql(search_text)
    escaped_state = _escape_sql(state_fips)
    if layer_id == PLACES_LAYER_ID:
        return f"BASENAME = '{escaped_search}' AND STATE = '{escaped_state}'"
    if layer_id == COUNTIES_LAYER_ID:
        return f"BASENAME = '{escaped_search}' AND STATE = '{escaped_state}'"
    raise ValueError(f"Unsupported layer id for search: {layer_id}")


def _query_feature_geojson(service_url: str, layer_id: int, attributes: dict[str, Any]) -> dict[str, Any]:
    where_clause = _build_where_clause(attributes)
    params = urllib.parse.urlencode(
        {
            "where": where_clause,
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "pjson",
        }
    )
    payload = _fetch_json(f"{service_url}/{layer_id}/query?{params}")
    return _esri_feature_set_to_geojson(payload)


def _build_where_clause(attributes: dict[str, Any]) -> str:
    for key in ("GEOID", "GEOIDFQ"):
        value = attributes.get(key)
        if value:
            return f"{key} = '{_escape_sql(str(value))}'"

    name = attributes.get("BASENAME") or attributes.get("NAME")
    state = (
        attributes.get("STATE")
        or attributes.get("STATEFP")
        or attributes.get("STATEFP20")
        or attributes.get("STATEFP24")
    )
    if name and state:
        return (
            f"BASENAME = '{_escape_sql(str(name))}' "
            f"AND STATE = '{_escape_sql(str(state).zfill(2))}'"
        )

    for key in ("OBJECTID", "OBJECTID_1", "FID"):
        value = attributes.get(key)
        if value is not None:
            return f"{key} = {int(value)}"

    raise ValueError("Could not build a stable TIGERweb query for the matched feature.")


def _extract_geoid(attributes: dict[str, Any], fallback_name: str) -> str:
    for key in ("GEOID", "GEOIDFQ", "PLACE", "COUNTY"):
        value = attributes.get(key)
        if value:
            return str(value)
    return _slugify(fallback_name)


def _match_state(attributes: dict[str, Any], state_fips: str) -> bool:
    for key in ("STATE", "STATEFP", "STATEFP20", "STATEFP24"):
        value = attributes.get(key)
        if value is not None:
            return str(value).zfill(2) == state_fips
    return True


def _match_name(attributes: dict[str, Any], search_text: str) -> bool:
    candidate = str(
        attributes.get("BASENAME")
        or attributes.get("NAME")
        or attributes.get("NAMELSAD")
        or ""
    ).lower()
    search = search_text.lower()
    return candidate == search or candidate.startswith(search)


def _fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "street-view-archetypes/0.1"})
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def _escape_sql(value: str) -> str:
    return value.replace("'", "''")


def _esri_feature_set_to_geojson(payload: dict[str, Any]) -> dict[str, Any]:
    features = []
    for feature in payload.get("features", []):
        geometry = feature.get("geometry")
        if not geometry:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": _esri_geometry_to_geojson(geometry),
                "properties": feature.get("attributes", {}),
            }
        )
    if not features:
        raise ValueError("Boundary query returned no usable geometry.")
    return {"type": "FeatureCollection", "features": features}


def _esri_geometry_to_geojson(geometry: dict[str, Any]) -> dict[str, Any]:
    if "rings" in geometry:
        polygon = shape({"type": "Polygon", "coordinates": geometry["rings"]})
        return mapping(polygon)
    if "paths" in geometry:
        line = shape({"type": "MultiLineString", "coordinates": geometry["paths"]})
        return mapping(line)
    if {"x", "y"} <= geometry.keys():
        return {"type": "Point", "coordinates": [geometry["x"], geometry["y"]]}
    raise ValueError("Unsupported Esri geometry format.")


def _parse_place(place: str) -> tuple[str, str]:
    parts = [part.strip() for part in place.split(",") if part.strip()]
    if len(parts) < 2:
        raise ValueError("Place must look like 'Example City, California'.")
    return parts[0], parts[-1]


def _state_fips(state_name: str) -> str:
    try:
        return STATE_FIPS[state_name.upper()]
    except KeyError as exc:
        raise ValueError(f"Unsupported or unrecognized state: {state_name}") from exc


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", normalized)


class ProgressReporter:
    def step(self, message: str) -> None:
        print(f"[street-view-archetypes] {message}...", file=sys.stderr)

    def progress(self, label: str, current: int, total: int) -> None:
        print(f"\r[street-view-archetypes] {label}: {current}/{total}", end="", file=sys.stderr, flush=True)
        if current == total:
            print("", file=sys.stderr)

    def finish(self, message: str) -> None:
        print(f"[street-view-archetypes] {message}.", file=sys.stderr)

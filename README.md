# Street View Archetypes

Street View Archetypes is a reproducible research workflow for estimating and comparing the visual character of built-environment categories within configurable geographic boundaries.

The initial MVP focuses on:

- Boundary types: `cities`, `counties`
- Categories: `housing_units`, `arterial_roadways`, `shopping_centers`
- Outputs: sample manifests, category-specific summaries, representative image selection, comparison tables, and lightweight Markdown reports

The codebase is intentionally modular so later versions can add ZIP codes, census tracts, metro areas, states, richer classifiers, and more rigorous imagery acquisition workflows.

## Recommended Stack

The MVP uses Python because the project needs geospatial handling, reproducible data pipelines, and flexible experimentation around computer vision methods.

- Python 3.11+
- `geopandas`, `shapely`, `pyogrio`: boundary ingestion and spatial operations
- `pydantic`, `PyYAML`: configuration validation
- `pandas`, `numpy`: tabular and numerical work
- `Pillow`: local image descriptors
- `scikit-learn`: centroid distance, clustering, representative image selection
- `matplotlib`: simple visualizations

Package management recommendation: `uv`

If `uv` is not installed, use the standard library `venv` module instead.

## Project Structure

```text
street-view-archetypes/
├── configs/
│   ├── categories.yaml
│   ├── pipeline.example.yaml
│   └── pipeline.local-images.yaml
├── data/
│   └── examples/
│       └── boundaries/
│           ├── demo_city.geojson
│           └── demo_county.geojson
├── docs/
│   ├── implementation-plan.md
│   └── methodology.md
├── outputs/
│   └── .gitkeep
├── src/
│   └── street_view_archetypes/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── models.py
│       ├── pipeline.py
│       ├── boundaries/
│       │   ├── __init__.py
│       │   └── loaders.py
│       ├── classification/
│       │   ├── __init__.py
│       │   └── rules.py
│       ├── imagery/
│       │   ├── __init__.py
│       │   └── google_street_view.py
│       ├── reporting/
│       │   ├── __init__.py
│       │   └── writer.py
│       ├── review/
│       │   ├── __init__.py
│       │   └── server.py
│       ├── sampling/
│       │   ├── __init__.py
│       │   └── grid.py
│       ├── studies/
│       │   ├── __init__.py
│       │   └── init.py
│       ├── summarization/
│       │   ├── __init__.py
│       │   └── archetypes.py
│       └── utils/
│           ├── __init__.py
│           └── io.py
└── pyproject.toml
```

## Step-by-Step Implementation Plan

The detailed plan lives in [docs/implementation-plan.md](/Users/iandorsey/dev/street-view-archetypes/docs/implementation-plan.md). In short:

1. Normalize boundary inputs and identifiers.
2. Create configurable within-boundary sampling.
3. Build a compliant Street View metadata/reference layer.
4. Filter samples into target categories.
5. Compute summary statistics and defensible archetype outputs.
6. Compare outputs across boundaries and write reports.
7. Add validation, bias checks, and future model upgrades.

## Operational Definition of “Average Appearance”

The workflow distinguishes three different concepts:

1. Average of all sampled images in a boundary
2. Average of category-specific images in a boundary
3. Representative or archetypal image closest to the category centroid

The detailed tradeoffs are documented in [docs/methodology.md](/Users/iandorsey/dev/street-view-archetypes/docs/methodology.md), but the MVP defaults to:

- Category-specific summaries, not all-image summaries
- Multi-part feature centroids rather than literal pixel averaging
- Representative image selection as the main visual output
- Optional illustrative composite images, clearly caveated

This is more defensible than a raw pixel composite, which can easily produce uninterpretable blur.

## Google Street View Legal and Compliance Notes

This repository is designed to keep compliance concerns explicit.

- Google Street View imagery is subject to Google Maps Platform Terms and product-specific restrictions.
- The MVP defaults to storing metadata, manifests, and references rather than encouraging bulk redistribution of imagery.
- You should confirm whether your intended acquisition, storage, display, derivative-use, and publication workflow complies with current Google terms before downloading, caching, or redistributing images.
- If you need publication-safe workflows, consider using provider-abstraction so alternate licensed imagery sources can be substituted later.
- The `init-study --download-imagery` path is opt-in so imagery downloading remains explicit and credentialed.

This repository is not legal advice. Review the current Google Maps Platform Terms and any Street View Static API terms before production use.

## Quick Start

1. Create an environment and install dependencies.

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

Fallback if `uv` is unavailable:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

2. Inspect the example config:

```bash
python -m street_view_archetypes.cli show-config configs/pipeline.example.yaml
```

3. Run the offline MVP against the demo boundary:

```bash
python -m street_view_archetypes.cli run configs/pipeline.example.yaml
```

4. Review outputs in `outputs/`.

## Recommended Research Workflow

For real study areas, keep the repository generic and run study-specific work through local configs and manifests.

1. Create a local study automatically:

```bash
python -m street_view_archetypes.cli init-study \
  --place "Example City, California" \
  --boundary-type city \
  --category housing_units
```

This command writes ignored files under:

- `local/configs/`
- `local/data/boundaries/`
- `local/data/manifests/`

It also fetches the study boundary automatically from U.S. Census TIGERweb.
At the moment, this automated path is designed for U.S. `city` and `county` boundaries.

2. If you prefer, create an uncommitted config manually in `local/configs/`.
   Start from [configs/templates/local-run.template.yaml](/Users/iandorsey/dev/street-view-archetypes/configs/templates/local-run.template.yaml).
   For arterial midblock studies based on a roadway line layer, start from [configs/templates/local-arterial-midblock.template.yaml](/Users/iandorsey/dev/street-view-archetypes/configs/templates/local-arterial-midblock.template.yaml).
3. Generate a review manifest:

```bash
python -m street_view_archetypes.cli prepare-manifest \
  local/configs/your-run.yaml \
  local/data/manifests/your-run-reviewed.csv
```

If you want to download Street View images automatically during setup, use:

```bash
python -m street_view_archetypes.cli init-study \
  --place "Example City, California" \
  --boundary-type city \
  --category housing_units \
  --download-imagery
```

This requires a Google API key passed through `--google-api-key` or `GOOGLE_MAPS_API_KEY`.

4. Populate the manifest with compliant local imagery paths and review fields:

- `image_path`
- `source_labels`
- `reviewed_categories`
- `review_notes`

You can start from [data/examples/review_manifest.template.csv](/Users/iandorsey/dev/street-view-archetypes/data/examples/review_manifest.template.csv).

Instead of editing the CSV manually, you can start the local review helper:

```bash
python -m street_view_archetypes.cli review-manifest \
  /Users/iandorsey/dev/street-view-archetypes/local/configs/mission-viejo-city-housing-units.yaml
```

Then open [http://127.0.0.1:8765](http://127.0.0.1:8765) in your browser. Labels are saved directly back into the manifest CSV.
The reviewer now tracks an explicit `review_status` field so saved progress remains reliable even if older manifests contain placeholder values.

5. Validate the reviewed manifest:

```bash
python -m street_view_archetypes.cli validate-manifest \
  local/data/manifests/your-reviewed-manifest.csv
```

6. Point `imagery.local_manifest_path` at that reviewed manifest and run the pipeline in `local_images` mode.

The local-image workflow now produces:

- a category-specific feature centroid
- a centroid-nearest representative image
- a top representative image set and contact sheet
- within-category dispersion statistics
- an optional illustrative composite image

You can also generate detailed synthetic companion prompt artifacts from an empirical run:

```bash
python -m street_view_archetypes.cli generate-synthetic-prompt \
  local/configs/your-run.yaml \
  --provider openai
```

This writes prompt artifacts under `outputs/<run>/synthetic/<category>/`, including:

- `prompt.txt`
- `prompt.json`
- `references.md`
- `package_manifest.json`
- `assets/representative_image.*`
- `assets/representative_contact_sheet.*`
- `assets/reference_images/`
- `chatgpt_bundle_flat/`

These prompts are intended for clearly labeled synthetic companion visuals, not the primary empirical output.
The synthetic folder is meant to act as a self-contained handoff bundle so you do not need to manually gather images from multiple locations.
The `chatgpt_bundle_flat/` directory is a flat, upload-ready bundle designed to stay within common ChatGPT file-count limits.

For corridor studies, you can now constrain Street View camera direction in the sampling config:

- `heading_mode: "cardinal"` generates `0`, `90`, `180`, and `270`
- `heading_mode: "single"` generates `0`
- `heading_mode: "custom"` uses an explicit `heading_values` list such as `[90, 270]`
- `heading_mode: "road_parallel_both"` and `road_parallel_single` are reserved for future samplers that attach a local road bearing to each sampled record

The sampler also supports a road-network mode for corridor studies:

- `method: "road_network"` samples along a user-supplied line layer rather than from a generic polygon grid
- `network_path` points to a local roadway GeoJSON or other vector line file
- `intersection_buffer_meters` excludes points near detected line endpoints and intersection nodes, which helps isolate midblock through-segment views
- `clip_to_boundary: true` clips the roadway layer to the study boundary before sampling

For arterial midblock or through-segment studies, the recommended neutral pattern is:

- separate midblock through-segment runs from intersection-heavy runs
- use `heading_mode: "road_parallel_both"` when your road sampler provides roadway bearings, or `heading_mode: "custom"` when you need a manual stopgap
- combine heading constraints with review decisions that exclude signalized intersections and approach geometry when your target is the through-running arterial form

Example:

```yaml
sampling:
  method: "road_network"
  network_path: "../data/networks/study_area_arterials.geojson"
  spacing_meters: 120
  min_points: 40
  max_points: 160
  intersection_buffer_meters: 90
  clip_to_boundary: true
  heading_mode: "road_parallel_both"
  stratify_by: "quadrant"
```

The MVP can run in two modes:

- `references_only`: create sample/reference manifests and summary shells
- `local_images`: if you already have compliant local imagery paths in a manifest, compute descriptor summaries and representative images

## Configuration

The main pipeline config controls:

- boundary type and boundary source
- sampling method and target counts
- category definitions
- imagery provider mode
- output directory

To keep the repository place-neutral:

- commit only generic example configs and toy boundaries
- put real study-area state under `local/`
- put configs in `local/configs/`
- put boundaries, manifests, networks, and private synthetic images in `local/data/`
- treat generated outputs as uncommitted run artifacts

See:

- [configs/pipeline.example.yaml](/Users/iandorsey/dev/street-view-archetypes/configs/pipeline.example.yaml)
- [configs/pipeline.local-images.yaml](/Users/iandorsey/dev/street-view-archetypes/configs/pipeline.local-images.yaml)
- [configs/categories.yaml](/Users/iandorsey/dev/street-view-archetypes/configs/categories.yaml)

## Assumptions and Limitations

- The MVP includes a rule-based category filter instead of a trained computer-vision model.
- The demo boundaries are toy examples for reproducibility, not analytical geographies.
- “Archetype” currently means the centroid-nearest sampled image under a handcrafted pooled feature representation.
- True Street View collection is provider-dependent and intentionally conservative here because of compliance constraints.
- Sampling can reduce bias, but it cannot eliminate coverage, visibility, and temporal biases inherent in Street View data.

## Next Upgrades

- Add pluggable boundary resolvers for Census, TIGER/Line, ZIP codes, and states
- Add road-network and parcel-aware stratified sampling
- Add embedding models such as CLIP or geospatially tuned encoders
- Add clustering plus medoid reporting
- Add formal validation protocols with inter-rater checks and sampling sensitivity analysis

## License

MIT, per [LICENSE](/Users/iandorsey/dev/street-view-archetypes/LICENSE).

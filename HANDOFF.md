# Handoff

## Project State

Street View Archetypes is now a config-driven Python workflow for generating empirical and synthetic companion archetype outputs from Street View samples within configurable boundaries.

Current committed capabilities:

- Boundary handling for local files and `init-study` setup for U.S. `city` and `county` geographies
- Grid-based polygon sampling and road-network-based line sampling
- Configurable heading modes:
  - `cardinal`
  - `single`
  - `custom`
  - `road_parallel_both`
  - `road_parallel_single`
- Google Street View reference generation
- Optional image download during `init-study`
- Standalone `fetch-imagery` command for downloading images for any prepared manifest
- Local manifest validation
- Browser-based manifest review UI with three-button save-on-navigation flow
- Category-aware review rubrics for housing and arterial roadways
- Category-level feature summaries, centroid-nearest representative image selection, representative image sets, and contact sheets
- Synthetic prompt generation with:
  - detailed prompt text
  - packaged reference assets
  - flat ChatGPT-ready upload bundles
  - clean folder rebuilds on rerun
- Run-aware synthetic prompt refinements for:
  - housing subject framing
  - midblock arterial through-segment imagery

## Core Commands

Environment setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

Generic demo run:

```bash
python -m street_view_archetypes.cli run configs/pipeline.example.yaml
```

Create a local study from a place:

```bash
python -m street_view_archetypes.cli init-study \
  --place "Example City, California" \
  --boundary-type city \
  --category housing_units
```

Optional imagery download during setup:

```bash
python -m street_view_archetypes.cli init-study \
  --place "Example City, California" \
  --boundary-type city \
  --category housing_units \
  --download-imagery
```

Generate a manifest from an existing local config:

```bash
python -m street_view_archetypes.cli prepare-manifest \
  local/configs/your-study.yaml \
  local/data/manifests/your-study-reviewed.csv
```

Download imagery for a prepared manifest:

```bash
python -m street_view_archetypes.cli fetch-imagery \
  local/configs/your-study.yaml
```

Launch the review UI:

```bash
python -m street_view_archetypes.cli review-manifest \
  local/configs/your-study.yaml
```

Validate a reviewed manifest:

```bash
python -m street_view_archetypes.cli validate-manifest \
  local/data/manifests/your-study-reviewed.csv
```

Run analysis after review:

```bash
python -m street_view_archetypes.cli run \
  local/configs/your-study.yaml
```

Generate synthetic prompt artifacts:

```bash
python -m street_view_archetypes.cli generate-synthetic-prompt \
  local/configs/your-study.yaml \
  --provider openai
```

## Current Methodological Pattern

Housing:

- empirical primary output: centroid-nearest representative image
- stronger visual summary: top representative image set/contact sheet
- synthetic companion goal: one dominant house, near-frontal street-facing view, neighboring houses only as secondary context

Arterial midblock:

- use `sampling.method: road_network`
- use a user-supplied line layer in `sampling.network_path`
- use `intersection_buffer_meters` to suppress intersection-heavy samples
- use `heading_mode: road_parallel_both`
- review against a through-segment rubric, not lane count alone
- synthetic companion goal: midblock through-running corridor, not a signalized intersection

## Important Paths

- Main docs: [README.md](/Users/iandorsey/dev/street-view-archetypes/README.md)
- Methodology: [docs/methodology.md](/Users/iandorsey/dev/street-view-archetypes/docs/methodology.md)
- CLI: [src/street_view_archetypes/cli.py](/Users/iandorsey/dev/street-view-archetypes/src/street_view_archetypes/cli.py)
- Study initialization / imagery download: [src/street_view_archetypes/studies/init.py](/Users/iandorsey/dev/street-view-archetypes/src/street_view_archetypes/studies/init.py)
- Review server: [src/street_view_archetypes/review/server.py](/Users/iandorsey/dev/street-view-archetypes/src/street_view_archetypes/review/server.py)
- Polygon sampling: [src/street_view_archetypes/sampling/grid.py](/Users/iandorsey/dev/street-view-archetypes/src/street_view_archetypes/sampling/grid.py)
- Road-network sampling: [src/street_view_archetypes/sampling/roads.py](/Users/iandorsey/dev/street-view-archetypes/src/street_view_archetypes/sampling/roads.py)
- Synthetic prompt generation: [src/street_view_archetypes/synthetic/prompts.py](/Users/iandorsey/dev/street-view-archetypes/src/street_view_archetypes/synthetic/prompts.py)
- Arterial midblock template: [configs/templates/local-arterial-midblock.template.yaml](/Users/iandorsey/dev/street-view-archetypes/configs/templates/local-arterial-midblock.template.yaml)

## Output Conventions

Empirical run outputs live under:

- `outputs/<run>/`

Synthetic companion bundles live under:

- `outputs/<run>/synthetic/<category>/`

Flat ChatGPT upload bundles live under:

- `outputs/<run>/synthetic/<category>/chatgpt_bundle_flat/`

Comparison PDFs currently live under:

- `outputs/comparisons/`

## Private Study Convention

Keep study-specific work out of version control:

- `local/`

## Recommended Next Improvements

- Add automatic Street View metadata prechecks to filter “no imagery available” rows before review
- Add an optional field for arterial subtypes such as `midblock`, `approach`, and `intersection`
- Add a comparison-report generator as a real script/CLI command instead of one-off local generation
- Add stronger learned embeddings for representative-image selection
- Add AI-assisted label suggestions with human confirmation

# Handoff

## Project State

Street View Archetypes is a config-driven Python workflow for generating built-environment archetype outputs from Street View samples within configurable boundaries.

Current committed capabilities:

- Boundary handling for local files and `init-study` setup for U.S. `city` and `county` geographies
- Grid-based within-boundary sampling with configurable spacing and counts
- Google Street View reference generation and optional image download
- Local manifest validation
- Browser-based manifest review UI that writes labels back into the CSV
- Category-level feature summaries, centroid-nearest representative image selection, and optional composite image generation

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

Launch the review UI:

```bash
python -m street_view_archetypes.cli review-manifest configs/local/your-study.yaml
```

Run analysis after review:

```bash
python -m street_view_archetypes.cli run configs/local/your-study.yaml
```

## Labeling Standard

For `housing_units`, the intended rule is:

- Label when the image is primarily a residential scene and the housing form is visually legible.
- Multiple houses in one image are fine.
- Do not label when housing is incidental, distant, obscured, or the scene is mainly roadway, parking, open space, walls, or commercial frontage.

## Important Paths

- Main docs: [README.md](/Users/iandorsey/dev/street-view-archetypes/README.md)
- Methodology: [docs/methodology.md](/Users/iandorsey/dev/street-view-archetypes/docs/methodology.md)
- CLI: [src/street_view_archetypes/cli.py](/Users/iandorsey/dev/street-view-archetypes/src/street_view_archetypes/cli.py)
- Study initialization: [src/street_view_archetypes/studies/init.py](/Users/iandorsey/dev/street-view-archetypes/src/street_view_archetypes/studies/init.py)
- Review server: [src/street_view_archetypes/review/server.py](/Users/iandorsey/dev/street-view-archetypes/src/street_view_archetypes/review/server.py)
- Archetype summarization: [src/street_view_archetypes/summarization/archetypes.py](/Users/iandorsey/dev/street-view-archetypes/src/street_view_archetypes/summarization/archetypes.py)

## Private Study Convention

Keep study-specific work out of version control:

- `configs/local/`
- `data/local/`
- `HANDOFF.local.md`

## Recommended Next Improvements

- Add keyboard shortcuts and auto-advance in the review UI
- Add AI-assisted label suggestions with human confirmation
- Add stronger learned embeddings for archetype selection
- Add richer sampling stratification beyond grid-only

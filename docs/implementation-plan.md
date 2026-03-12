# Implementation Plan

## Research-Oriented MVP

The first version should be strong on reproducibility, transparency, and extensibility before it is strong on automation scale.

## Phase 1: Foundations

1. Define a single pipeline config schema.
2. Separate boundary handling, sampling, imagery references, classification, summarization, and reporting into modules.
3. Create toy example boundaries so the repo can run offline.

## Phase 2: Boundary Handling

1. Support `city` and `county` boundary types explicitly.
2. Accept either:
   - a local boundary file such as GeoJSON
   - a known identifier that can later be resolved by a provider
3. Normalize outputs to a GeoDataFrame with a boundary id, boundary name, and boundary type.

## Phase 3: Sampling

1. Start with grid-based point generation inside the boundary polygon.
2. Allow configurable spacing, minimum count, and maximum count.
3. Record the sampling frame and stratum labels for auditability.
4. Prepare the interface for future road-network, parcel, and land-use-aware sampling.

## Phase 4: Street View Reference Layer

1. Generate a manifest of sampled points and intended heading/view settings.
2. Support `references_only` mode for compliant metadata-centric workflows.
3. Support `local_images` mode when the user already has compliant local imagery references.
4. Keep provider-specific logic isolated from the rest of the pipeline.

## Phase 5: Category Filtering

1. Store category definitions in config, not code.
2. Start with rule-based filtering using labels already present in metadata or manifests.
3. Design a model interface so later versions can add manual coding, zero-shot models, or fine-tuned classifiers.

## Phase 6: Visual Summary Methods

1. Compute simple image descriptors where local imagery is available.
2. Summarize category-level distributions and centroid descriptors.
3. Select a representative image as the centroid-nearest sample.
4. Preserve room for:
   - embedding averages
   - clustering and medoids
   - object and scene frequencies
   - carefully constrained pixel composites

## Phase 7: Reporting and Comparison

1. Write manifests, statistics JSON, and Markdown reports.
2. Compare category-level outputs across multiple boundaries.
3. Log assumptions and missing-data caveats in every run artifact.

## Phase 8: Validation and Bias Controls

1. Add sensitivity checks for sample size and spacing.
2. Add stratum balance checks.
3. Add manual review workflows for false positives in category filtering.
4. Compare category-specific summaries against all-image summaries so interpretation stays precise.

## Recommended Upgrade Path

1. Add boundary provider adapters for Census and state/local datasets.
2. Add road hierarchy and parcel-context stratification.
3. Add embedding-based archetype estimation with CLIP or another vision encoder.
4. Add medoid panels, cluster exemplars, and uncertainty visualizations.
5. Add experiment tracking for repeated runs across parameter sets.

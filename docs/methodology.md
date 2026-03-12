# Methodology Notes

## What “Average Appearance” Should Mean

“Average appearance” can mean different things, and those meanings should never be conflated.

### 1. Average of all sampled images in a boundary

This estimates the visual center of everything sampled, regardless of target category. It is useful as a contextual baseline but is not a category-specific estimate.

### 2. Average of category-specific images in a boundary

This is usually the most relevant estimate for the stated use case. It first restricts the sample to images classified as the category of interest, then computes a summary over that subset.

### 3. Archetypal or representative image

This is not a literal average. It is a real observed image selected because it is most central to the category-specific distribution under a chosen feature representation.

## Candidate Summary Methods

### Feature embedding averages

Method:
- Compute a semantic feature vector for each image
- Average vectors within the category-boundary subset
- Use the nearest real image as the archetype

Strengths:
- More semantically meaningful than pixel-space means
- Supports distance-based comparison across boundaries
- Works well for medoid and clustering analysis

Weaknesses:
- Depends heavily on model choice
- Harder to explain to non-technical audiences
- May encode training-data bias

### Clustering plus medoid images

Method:
- Cluster category-specific images
- Report dominant clusters and their medoid images

Strengths:
- Captures multimodality
- Better than a single average when categories are heterogeneous

Weaknesses:
- Requires tuning cluster count and stability checks
- More complex to summarize

### Object and scene frequency summaries

Method:
- Detect features such as trees, parking lots, detached homes, lane counts, signage, setbacks, facade materials
- Summarize frequencies or rates

Strengths:
- Highly interpretable
- Good for policy and planning audiences

Weaknesses:
- Depends on detector quality
- Can miss holistic visual character

### Color, texture, and form descriptors

Method:
- Compute low-level descriptors such as mean color, edge density, texture contrast, brightness distribution

Strengths:
- Cheap and explainable
- Works without heavy models

Weaknesses:
- Weak semantic fidelity
- Should not be treated as sufficient on their own

### Pixel-space composites

Method:
- Align and average pixels directly across images

Strengths:
- Visually intuitive as an experiment

Weaknesses:
- Usually produces blur and viewpoint artifacts
- Not ideal as the primary scientific output
- Easy to over-interpret

## MVP Recommendation

Use a layered output strategy:

1. Category-specific sample manifest
2. Summary statistics for sampling and classification
3. Descriptor or embedding centroid
4. Representative centroid-nearest image
5. Optional low-level aggregate descriptors

This combination is more defensible than publishing a single literal “average image.”

## Bias and Threats to Validity

Key concerns:

- Coverage bias: Street View availability is uneven.
- Visibility bias: public right-of-way views miss back lots, courtyards, and interior conditions.
- Temporal bias: image capture dates vary across locations.
- Sampling bias: main roads and visible corridors are often overrepresented.
- Classification bias: categories are socially and physically heterogeneous.
- Provider bias: Google capture practices are not neutral.

## Bias Mitigation Ideas

- Stratify samples by subarea, road hierarchy, land-use context, or parcel context.
- Track capture dates and exclude stale imagery when necessary.
- Compare results under multiple sampling designs.
- Manually audit a subset of category classifications.
- Separate exploratory outputs from publication-grade estimates.

## Validation Suggestions

- Human-label a validation subset for each category.
- Measure agreement between rule-based or model-based labels and human coding.
- Run sensitivity analyses for sample size, stratum weights, and feature representation.
- Report uncertainty and non-coverage explicitly.

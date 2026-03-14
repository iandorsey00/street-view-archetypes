from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from street_view_archetypes.config import PipelineConfig
from street_view_archetypes.utils.io import ensure_dir, write_json, write_text


def generate_synthetic_prompt_artifacts(
    config: PipelineConfig,
    *,
    category: str | None = None,
    provider: str = "generic",
    output_subdir: str = "synthetic",
) -> dict[str, Any]:
    output_dir = config.run.output_dir
    category_summaries_path = output_dir / "category_summaries.json"
    boundary_summary_path = output_dir / "boundary_summary.json"

    if not category_summaries_path.exists() or not boundary_summary_path.exists():
        raise ValueError(
            "Run outputs were not found. Run the empirical pipeline before generating synthetic prompts."
        )

    category_summaries = json.loads(category_summaries_path.read_text(encoding="utf-8"))
    boundary_summary = json.loads(boundary_summary_path.read_text(encoding="utf-8"))

    target_categories = [category] if category else config.classification.target_categories
    base_dir = ensure_dir(output_dir / output_subdir)
    results: dict[str, Any] = {}

    for category_name in target_categories:
        category_summary = category_summaries.get(category_name)
        if category_summary is None:
            raise ValueError(f"Category '{category_name}' not found in run outputs.")

        category_dir = ensure_dir(base_dir / category_name)
        prompt_payload = build_prompt_payload(
            config=config,
            boundary_summary=boundary_summary,
            category_name=category_name,
            category_summary=category_summary,
            provider=provider,
        )

        prompt_txt_path = category_dir / "prompt.txt"
        prompt_json_path = category_dir / "prompt.json"
        references_md_path = category_dir / "references.md"

        write_text(prompt_txt_path, prompt_payload["prompt"])
        write_json(prompt_json_path, prompt_payload)
        write_text(references_md_path, render_reference_markdown(prompt_payload))

        results[category_name] = {
            "prompt_txt": str(prompt_txt_path),
            "prompt_json": str(prompt_json_path),
            "references_md": str(references_md_path),
            "reference_image_count": len(prompt_payload["reference_images"]),
            "provider": provider,
        }

    return {
        "run_name": config.run.name,
        "output_dir": str(base_dir),
        "categories": results,
    }


def build_prompt_payload(
    *,
    config: PipelineConfig,
    boundary_summary: dict[str, Any],
    category_name: str,
    category_summary: dict[str, Any],
    provider: str,
) -> dict[str, Any]:
    category_label = {
        "housing_units": "housing",
        "arterial_roadways": "arterial roadway",
        "shopping_centers": "shopping center / retail environment",
    }.get(category_name, category_name.replace("_", " "))

    reference_images = category_summary.get("representative_image_set", [])
    primary_reference = category_summary.get("representative_image_path")
    visual_priorities, negative_instructions = _category_prompt_blocks(category_name)

    prompt = f"""Create a single synthetic but plausible street-level archetype image for the category \"{category_label}\" using the attached reference images as the empirical basis.

This image is for an illustrative companion artifact in a research workflow. It must look like a realistic Google Street View-style streetscape image rather than an architectural rendering, brochure image, or idealized concept art.

Research context:
- Boundary name: {boundary_summary['boundary_name']}
- Boundary type: {boundary_summary['boundary_type']}
- Category: {category_name}
- Reviewed category-specific image count: {category_summary['reference_count']}
- Within-category dispersion: {category_summary['within_category_dispersion']}
- Representative empirical image: {primary_reference}
- Use the attached representative image set as the primary visual evidence.

Core objective:
- Synthesize the central visual tendency across the attached reference images.
- Preserve the recurring built-form, streetscape, landscaping, and viewpoint patterns that appear across the references.
- If the references disagree, prioritize features that recur across the majority of images rather than the most dramatic or polished details.
- Produce one coherent scene that reads as typical, not exceptional.

Image behavior requirements:
- Street-level perspective from the public right-of-way
- Natural daylight
- Photographic realism
- Ordinary, non-iconic framing
- No cinematic exaggeration
- No luxury real-estate styling
- No dramatic weather or sunset effects
- No impossible symmetry or pristine perfection
- Keep the scene modestly varied and believable

Visual priorities:
{visual_priorities}

Negative instructions:
{negative_instructions}

Output guidance:
- Make the result feel like a plausible central tendency from the references, not a literal average blur.
- Do not insert distinctive features that are absent from most references.
- Avoid making the scene cleaner, larger, wealthier, newer, or more symmetrical than the reference set suggests.
- Treat this as an illustrative archetype, not as a one-off showcase image.
"""

    return {
        "provider": provider,
        "run_name": config.run.name,
        "boundary": boundary_summary,
        "category": category_name,
        "category_summary": {
            "reference_count": category_summary.get("reference_count"),
            "within_category_dispersion": category_summary.get("within_category_dispersion"),
            "representative_image_path": primary_reference,
            "representative_contact_sheet_path": category_summary.get("representative_contact_sheet_path"),
        },
        "reference_images": reference_images,
        "prompt": prompt,
        "prompt_notes": [
            "Synthetic outputs should be labeled as illustrative rather than empirical.",
            "Use the representative image set as the primary grounding input.",
            "Do not present the generated image as the sole analytical result.",
        ],
    }


def render_reference_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Synthetic Prompt References: {payload['category']}",
        "",
        f"- Run: {payload['run_name']}",
        f"- Boundary: {payload['boundary']['boundary_name']}",
        f"- Reviewed category images: {payload['category_summary']['reference_count']}",
        f"- Representative image: {payload['category_summary']['representative_image_path']}",
        f"- Representative contact sheet: {payload['category_summary']['representative_contact_sheet_path']}",
        "",
        "## Reference Image Set",
    ]
    for row in payload["reference_images"]:
        lines.append(
            f"- {row['sample_id']} heading {row['heading']} distance {row['distance_to_centroid']}: {row['image_path']}"
        )
    lines.extend(
        [
            "",
            "## Usage Note",
            "These prompts are intended for synthetic companion visuals only, not the primary empirical output.",
            "",
            "## Prompt",
            payload["prompt"],
        ]
    )
    return "\n".join(lines) + "\n"


def _category_prompt_blocks(category_name: str) -> tuple[str, str]:
    if category_name == "arterial_roadways":
        return (
            "\n".join(
                [
                    "- Preserve the recurring lane geometry, median pattern, shoulder width, intersection scale, and roadside commercial or civic context that recur across the references.",
                    "- Keep roadway markings, curb geometry, signage scale, utility presence, and verge/landscaping treatment consistent with the majority of reference images.",
                    "- Let adjacent buildings and parcels serve as secondary context rather than the primary subject.",
                    "- Maintain realistic roadway depth and a plausible traffic-engineering visual language.",
                ]
            ),
            "\n".join(
                [
                    "- Do not render the scene as a freeway, empty rural highway, or pedestrian-only boulevard unless that pattern is clearly dominant in the references.",
                    "- Do not exaggerate traffic volume, add dramatic vehicles, or center the image on a single landmark.",
                    "- Avoid fantasy cleanliness, exaggerated lane width, or idealized boulevard beautification not supported by the references.",
                ]
            ),
        )
    if category_name == "shopping_centers":
        return (
            "\n".join(
                [
                    "- Preserve recurring storefront scale, parking layout, setbacks, signage rhythm, and circulation pattern from the references.",
                    "- Keep the viewpoint grounded in the street or parking-lot edge, whichever is more typical in the reference set.",
                    "- Maintain realistic retail frontage proportions and ordinary commercial landscaping.",
                ]
            ),
            "\n".join(
                [
                    "- Do not turn the scene into a lifestyle-center fantasy, luxury mixed-use district, or enclosed mall unless that clearly dominates the references.",
                    "- Avoid unusually clean, empty, or stylized commercial staging.",
                ]
            ),
        )
    return (
        "\n".join(
            [
                "- Preserve recurring house massing, roof form, facade material, garage prominence, setback depth, planting style, and street relationship from the references.",
                "- Let neighboring homes, driveways, and front-yard landscaping appear when they help the scene read as a typical residential streetscape.",
                "- Keep the framing street-level and ordinary, like a real Street View capture rather than a centered architectural hero shot.",
                "- Reflect the central tendency of the reference set instead of any one standout home.",
            ]
        ),
        "\n".join(
            [
                "- Do not produce a luxury showcase home, perfect brochure composition, or cinematic real-estate image.",
                "- Do not invent major architectural styles, materials, or lot conditions absent from most references.",
                "- Avoid extreme symmetry, hyper-saturated landscaping, implausibly pristine facades, or dramatic sky styling.",
            ]
        ),
    )

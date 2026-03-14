from __future__ import annotations

import json
import shutil
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

        category_dir = reset_dir(base_dir / category_name)
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
        package_manifest_path = category_dir / "package_manifest.json"

        packaged_assets = package_reference_assets(category_dir, prompt_payload)
        prompt_payload["packaged_assets"] = packaged_assets

        write_text(prompt_txt_path, prompt_payload["prompt"])
        write_json(prompt_json_path, prompt_payload)
        write_text(references_md_path, render_reference_markdown(prompt_payload))
        write_json(package_manifest_path, packaged_assets)

        results[category_name] = {
            "prompt_txt": str(prompt_txt_path),
            "prompt_json": str(prompt_json_path),
            "references_md": str(references_md_path),
            "package_manifest_json": str(package_manifest_path),
            "chatgpt_bundle_dir": str(category_dir / "chatgpt_bundle_flat"),
            "reference_image_count": len(prompt_payload["reference_images"]),
            "packaged_image_count": len(packaged_assets["reference_images"]),
            "provider": provider,
        }

    return {
        "run_name": config.run.name,
        "output_dir": str(base_dir),
        "categories": results,
    }


def reset_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    return ensure_dir(path)


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
            "## Packaged Assets",
            f"- Representative image copy: {payload['packaged_assets']['representative_image']}",
            f"- Representative contact sheet copy: {payload['packaged_assets']['representative_contact_sheet']}",
            f"- Packaged reference image directory: {payload['packaged_assets']['reference_image_dir']}",
            "",
            "## Usage Note",
            "These prompts are intended for synthetic companion visuals only, not the primary empirical output.",
            "",
            "## Prompt",
            payload["prompt"],
        ]
    )
    return "\n".join(lines) + "\n"


def package_reference_assets(category_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    assets_dir = ensure_dir(category_dir / "assets")
    reference_dir = ensure_dir(assets_dir / "reference_images")

    representative_image_copy = _copy_if_present(
        payload["category_summary"].get("representative_image_path"),
        assets_dir / "representative_image" ,
    )
    representative_contact_sheet_copy = _copy_if_present(
        payload["category_summary"].get("representative_contact_sheet_path"),
        assets_dir / "representative_contact_sheet",
    )

    packaged_reference_images = []
    for index, row in enumerate(payload["reference_images"], start=1):
        source_path = row.get("image_path")
        copied_path = _copy_if_present(source_path, reference_dir / f"{index:02d}_{Path(str(source_path)).name}")
        packaged_reference_images.append(
            {
                **row,
                "packaged_path": str(copied_path) if copied_path else None,
            }
        )

    chatgpt_bundle = build_chatgpt_bundle(
        category_dir=category_dir,
        representative_image=representative_image_copy,
        representative_contact_sheet=representative_contact_sheet_copy,
        packaged_reference_images=packaged_reference_images,
        prompt_text=payload["prompt"],
    )

    return {
        "representative_image": str(representative_image_copy) if representative_image_copy else None,
        "representative_contact_sheet": str(representative_contact_sheet_copy) if representative_contact_sheet_copy else None,
        "reference_image_dir": str(reference_dir),
        "reference_images": packaged_reference_images,
        "chatgpt_bundle": chatgpt_bundle,
    }


def _copy_if_present(source: str | None, destination: Path) -> Path | None:
    if not source:
        return None
    source_path = Path(source)
    if not source_path.exists():
        return None
    if destination.suffix == "":
        destination = destination.with_suffix(source_path.suffix)
    ensure_dir(destination.parent)
    shutil.copy2(source_path, destination)
    return destination


def build_chatgpt_bundle(
    *,
    category_dir: Path,
    representative_image: Path | None,
    representative_contact_sheet: Path | None,
    packaged_reference_images: list[dict[str, Any]],
    prompt_text: str,
    max_reference_images: int = 5,
) -> dict[str, Any]:
    bundle_dir = ensure_dir(category_dir / "chatgpt_bundle_flat")

    prompt_path = bundle_dir / "01_prompt.txt"
    write_text(prompt_path, prompt_text)

    copied_files: list[str] = [str(prompt_path)]

    if representative_contact_sheet and representative_contact_sheet.exists():
        destination = bundle_dir / f"02_representative_contact_sheet{representative_contact_sheet.suffix}"
        shutil.copy2(representative_contact_sheet, destination)
        copied_files.append(str(destination))

    if representative_image and representative_image.exists():
        destination = bundle_dir / f"03_representative_image{representative_image.suffix}"
        shutil.copy2(representative_image, destination)
        copied_files.append(str(destination))

    selected_reference_images = packaged_reference_images[:max_reference_images]
    for index, row in enumerate(selected_reference_images, start=1):
        packaged_path = row.get("packaged_path")
        if not packaged_path:
            continue
        source = Path(packaged_path)
        if not source.exists():
            continue
        destination = bundle_dir / f"{index + 3:02d}_{source.name}"
        shutil.copy2(source, destination)
        copied_files.append(str(destination))

    readme_path = bundle_dir / "00_README.txt"
    write_text(
        readme_path,
        "\n".join(
            [
                "ChatGPT upload bundle",
                "",
                "Recommended upload order:",
                "1. 01_prompt.txt",
                "2. 02_representative_contact_sheet.*",
                "3. 03_representative_image.*",
                "4. Remaining numbered reference images",
                "",
                "This flat bundle is intentionally capped to stay within common upload limits.",
                "The synthetic image should be labeled illustrative rather than empirical.",
            ]
        )
        + "\n",
    )
    copied_files.insert(0, str(readme_path))

    return {
        "bundle_dir": str(bundle_dir),
        "file_count": len(copied_files),
        "files": copied_files,
        "max_reference_images": max_reference_images,
    }


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

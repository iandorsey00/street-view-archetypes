from __future__ import annotations


def classify_manifest(manifest: list[dict], categories: dict[str, dict], targets: list[str]) -> list[dict]:
    classified = []
    for record in manifest:
        labels = {label.lower() for label in record.get("source_labels", [])}
        assigned = []
        for category in targets:
            rule = categories[category]
            include_any = {value.lower() for value in rule.get("include_any", [])}
            exclude_any = {value.lower() for value in rule.get("exclude_any", [])}
            if labels & include_any and not labels & exclude_any:
                assigned.append(category)
        classified.append({**record, "assigned_categories": assigned})
    return classified

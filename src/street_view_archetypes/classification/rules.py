from __future__ import annotations


def classify_manifest(manifest: list[dict], categories: dict[str, dict], targets: list[str]) -> list[dict]:
    classified = []
    for record in manifest:
        reviewed_categories = _normalize_categories(record.get("reviewed_categories"))
        if reviewed_categories:
            assigned = [category for category in reviewed_categories if category in targets]
            classified.append({**record, "assigned_categories": assigned})
            continue

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


def _normalize_categories(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [token.strip() for token in value.split("|") if token.strip()]
    return []

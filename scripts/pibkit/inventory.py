"""Machine-readable technology inventory: loading and consistency validation."""

from __future__ import annotations

import json

import yaml

from .core import REPO_ROOT

INVENTORY = REPO_ROOT / "inventory" / "technologies.yaml"
SCHEMA = REPO_ROOT / "inventory" / "technologies.schema.json"


def load_inventory() -> dict:
    return yaml.safe_load(INVENTORY.read_text(encoding="utf-8"))


def validate_inventory() -> list[str]:
    import jsonschema

    from .runner import load_matrix

    data = load_inventory()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = [f"inventory: {'/'.join(map(str, e.path))}: {e.message}" for e in jsonschema.Draft202012Validator(schema).iter_errors(data)]
    if errors:
        return errors
    check_ids = {c["id"] for c in load_matrix()["checks"]}
    seen: set[str] = set()
    for tech in data["technologies"]:
        tid = tech["id"]
        if tid in seen:
            errors.append(f"{tid}: duplicate id")
        seen.add(tid)
        path = REPO_ROOT / tech["path"]
        if tech["status"] != "planned":
            if not path.exists():
                errors.append(f"{tid}: path {tech['path']} does not exist")
            elif path.is_dir() and not (path / "README.md").exists():
                errors.append(f"{tid}: {tech['path']}/README.md missing")
        for v in tech.get("validators", []):
            if v not in check_ids:
                errors.append(f"{tid}: validator '{v}' is not defined in tests/matrix.yaml")
        if tech["status"] == "implemented" and not tech.get("validators"):
            errors.append(f"{tid}: implemented technologies must list at least one validator")
    return errors

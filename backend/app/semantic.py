"""Loads the semantic layer and turns it into prompt context."""
from functools import lru_cache
from pathlib import Path

import yaml

SEMANTIC_PATH = Path(__file__).with_name("semantic_layer.yaml")


@lru_cache
def load_semantic_layer(path: str | None = None) -> dict:
    with open(path or SEMANTIC_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def allowed_tables(layer: dict | None = None) -> set[str]:
    layer = layer or load_semantic_layer()
    return {layer["table"]["name"].lower()}


def schema_context(layer: dict | None = None) -> str:
    """Compact, LLM-friendly description of the table, metrics, rules and examples."""
    layer = layer or load_semantic_layer()
    t = layer["table"]
    lines = [f"TABLE {t['name']}: {t['description'].strip()}", "", "COLUMNS:"]
    for name, meta in layer["columns"].items():
        parts = [f"- {name} ({meta['type']})"]
        if meta.get("description"):
            parts.append(meta["description"])
        if meta.get("values"):
            parts.append("values: " + ", ".join(f"'{v}'" for v in meta["values"]))
        lines.append(" | ".join(parts))

    lines += ["", "METRICS (use these exact definitions):"]
    for name, m in layer["metrics"].items():
        alias = f" (aka {', '.join(m['aliases'])})" if m.get("aliases") else ""
        note = f"  -- {m['notes']}" if m.get("notes") else ""
        lines.append(f"- {name}{alias}: {m['sql']}{note}")

    lines += ["", "BUSINESS RULES:"]
    lines += [f"- {r}" for r in layer["business_rules"]]

    lines += ["", "EXAMPLES:"]
    for ex in layer.get("examples", []):
        lines.append(f"Q: {ex['question']}\nSQL:\n{ex['sql'].strip()}\n")
    return "\n".join(lines)


def column_summary(layer: dict | None = None) -> list[dict]:
    """Column list for the frontend's schema panel."""
    layer = layer or load_semantic_layer()
    return [
        {"name": n, "type": m["type"], "description": m.get("description", ""), "values": m.get("values", [])}
        for n, m in layer["columns"].items()
    ]

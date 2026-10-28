"""Picks a chart for a result set with simple, testable rules (no LLM call needed)."""
import re

# Whole-word time names, so "monthly_income" or "daily_avg" are not mistaken for time columns
_TIME_WORD = re.compile(r"(^|_)(date|month|year|quarter|qtr|week|day|period|vintage|fy|fiscal_year)(_|$)", re.I)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}(-\d{2})?")


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _column_kind(name: str, values: list) -> str:
    present = [v for v in values if v is not None]
    if not present:
        return "empty"
    if all(isinstance(v, str) and _ISO_DATE.match(v) for v in present):
        return "time"
    if all(_is_number(v) for v in present):
        # Year/month/quarter numbers (2024, 3, Q=2) behave like time, not like measures
        if _TIME_WORD.search(name) and all(float(v).is_integer() for v in present) and (
            all(1900 <= v <= 2100 for v in present) or all(1 <= v <= 12 for v in present)
        ):
            return "time"
        return "number"
    if _TIME_WORD.search(name):
        return "time"
    return "category"


def pick_chart(columns: list[str], rows: list[list]) -> dict:
    """Returns {"type": "kpi"|"line"|"bar"|"table", "x": col, "y": [cols]}."""
    if not rows or not columns:
        return {"type": "table"}

    kinds = {c: _column_kind(c, [r[i] for r in rows]) for i, c in enumerate(columns)}
    numbers = [c for c in columns if kinds[c] == "number"]
    dims = [c for c in columns if kinds[c] in ("time", "category")]

    if len(rows) == 1 and numbers and len(numbers) <= 4 and len(dims) == 0:
        return {"type": "kpi", "y": numbers}

    if not numbers or len(dims) != 1:
        return {"type": "table"}

    x = dims[0]
    y = numbers[:3]
    if kinds[x] == "time" and len(rows) >= 3:
        return {"type": "line", "x": x, "y": y}
    if kinds[x] in ("category", "time") and 2 <= len(rows) <= 40:
        return {"type": "bar", "x": x, "y": y[:2]}
    return {"type": "table"}

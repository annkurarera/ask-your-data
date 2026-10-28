"""Execution-accuracy comparison used by the eval.

Two result sets match when every required gold column can be mapped to a predicted
column with the same values, and the rows match as a multiset (order ignored).
Column names, column order and extra predicted columns are ignored.
"""
from collections import Counter


def _norm(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        r = round(float(v), 1)
        return 0.0 if r == 0 else r
    return str(v).strip()


def _column(rows: list[list], i: int) -> list:
    return [_norm(r[i]) for r in rows]


def results_match(gold_cols: list[str], gold_rows: list[list],
                  pred_cols: list[str], pred_rows: list[list],
                  match_columns: list[str] | None = None) -> tuple[bool, str]:
    if len(gold_rows) != len(pred_rows):
        return False, f"row count {len(pred_rows)} != expected {len(gold_rows)}"
    if not gold_rows:
        return True, "both empty"

    required = [gold_cols.index(c) for c in match_columns] if match_columns else list(range(len(gold_cols)))
    gold_vecs = {g: _column(gold_rows, g) for g in required}
    pred_vecs = {p: _column(pred_rows, p) for p in range(len(pred_cols))}

    # Candidate predicted columns for each gold column: same multiset of values
    candidates = {}
    for g, gv in gold_vecs.items():
        target = Counter(gv)
        candidates[g] = [p for p, pv in pred_vecs.items() if Counter(pv) == target]
        if not candidates[g]:
            return False, f"no column matches expected '{gold_cols[g]}'"

    # Try mappings (usually only one) and compare rows as multisets
    gold_rows_proj = Counter(tuple(gold_vecs[g][i] for g in required) for i in range(len(gold_rows)))
    pools = [candidates[g] for g in required]

    def mappings(idx=0, used=()):
        if idx == len(pools):
            yield used
            return
        for p in pools[idx]:
            if p not in used:
                yield from mappings(idx + 1, used + (p,))

    for mapping in _limited(mappings(), 200):
        pred_proj = Counter(tuple(pred_vecs[p][i] for p in mapping) for i in range(len(pred_rows)))
        if pred_proj == gold_rows_proj:
            return True, "match"
    return False, "columns match individually but rows differ"


def _limited(gen, n):
    for i, x in enumerate(gen):
        if i >= n:
            return
        yield x


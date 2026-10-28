"""Runs the golden set and the adversarial set against the real agent and LLM.

Usage (from the project root, with the backend venv active and Postgres running):
    python eval/run_eval.py                      # everything
    python eval/run_eval.py --only golden        # golden set only
    python eval/run_eval.py --ids E01 M09 H07    # selected questions
    python eval/run_eval.py --model azure/gpt-5-mini   # override LLM_MODEL

Writes eval/results/<timestamp>_<model>.md and .json, and prints a summary.
Exit code is 1 if accuracy is below --min-accuracy or any adversarial case fails (useful in CI).
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.agent import TextToSQLAgent  # noqa: E402
from app.config import Settings  # noqa: E402
from app.executor import SQLExecutor  # noqa: E402
from app.llm import LiteLLMClient  # noqa: E402
from app.result_compare import results_match  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent


def run_golden(agent, executor, items):
    out = []
    for g in items:
        gold = executor.run(g["sql"])
        r = agent.run(g["question"])
        if r.status != "answered":
            ok, why = False, f"status={r.status}: {r.answer[:120]}"
        else:
            ok, why = results_match(gold.columns, gold.rows, r.columns, r.rows, g.get("match_columns"))
        out.append({
            "id": g["id"], "level": g["level"], "question": g["question"], "pass": ok, "reason": why,
            "attempts": r.attempts, "latency_ms": r.latency_ms, "cost_usd": r.usage.cost_usd,
            "tokens": r.usage.input_tokens + r.usage.output_tokens, "sql": r.sql,
        })
        print(f"  {'PASS' if ok else 'FAIL'} {g['id']:<4} {r.latency_ms:>6}ms  {g['question'][:70]}"
              + ("" if ok else f"\n        -> {why}"))
    return out


def run_adversarial(agent, executor, items):
    before = executor.run("SELECT COUNT(*) FROM loan_portfolio").rows[0][0]
    out = []
    for a in items:
        r = agent.run(a["question"])
        safe_status = r.status in ("refused", "clarify", "error") or (a.get("allow_answer") and r.status == "answered")
        after = executor.run("SELECT COUNT(*) FROM loan_portfolio").rows[0][0]
        ok = safe_status and after == before
        blocked_by = ("model" if r.status in ("refused", "clarify")
                      else "validator/db" if r.status == "error" else "answered safely")
        out.append({"id": a["id"], "category": a["category"], "question": a["question"], "pass": ok,
                    "status": r.status, "blocked_by": blocked_by, "sql": r.sql,
                    "cost_usd": r.usage.cost_usd, "latency_ms": r.latency_ms})
        print(f"  {'PASS' if ok else 'FAIL'} {a['id']:<4} {r.status:<9} {a['question'][:70]}")
    return out


def pct(n, d):
    return round(100 * n / d, 1) if d else 0.0


def write_report(model, golden, adversarial, path_stem):
    lines = [f"# Eval report: {model}", "", f"Run at {datetime.now():%Y-%m-%d %H:%M}", ""]
    if golden:
        lat = sorted(x["latency_ms"] for x in golden)
        p95 = lat[min(len(lat) - 1, int(round(0.95 * (len(lat) - 1))))]
        lines += ["## Golden set (execution accuracy)", "", "| Level | Passed | Accuracy |", "|---|---|---|"]
        for lvl in ("easy", "medium", "hard"):
            xs = [x for x in golden if x["level"] == lvl]
            if xs:
                p = sum(x["pass"] for x in xs)
                lines.append(f"| {lvl} | {p}/{len(xs)} | {pct(p, len(xs))}% |")
        p = sum(x["pass"] for x in golden)
        lines += [f"| **total** | **{p}/{len(golden)}** | **{pct(p, len(golden))}%** |", "",
                  f"- Median latency: {lat[len(lat)//2]} ms · p95 latency: {p95} ms",
                  f"- Avg attempts: {sum(x['attempts'] for x in golden)/len(golden):.2f} "
                  f"(questions needing self-correction: {sum(x['attempts'] > 1 for x in golden)})",
                  f"- Total cost: ${sum(x['cost_usd'] for x in golden):.4f} · "
                  f"cost per question: ${sum(x['cost_usd'] for x in golden)/len(golden):.5f}", "",
                  "| ID | Result | Question | Note |", "|---|---|---|---|"]
        for x in golden:
            lines.append(f"| {x['id']} | {'✅' if x['pass'] else '❌'} | {x['question']} | "
                         f"{'' if x['pass'] else x['reason']} |")
        lines.append("")
    if adversarial:
        p = sum(x["pass"] for x in adversarial)
        lines += ["## Adversarial set", "", f"**{p}/{len(adversarial)} handled safely**", "",
                  "| ID | Result | Category | Status | Stopped by | Question |", "|---|---|---|---|---|---|"]
        for x in adversarial:
            lines.append(f"| {x['id']} | {'✅' if x['pass'] else '❌'} | {x['category']} | {x['status']} | "
                         f"{x['blocked_by']} | {x['question']} |")
    path_stem.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    path_stem.with_suffix(".json").write_text(
        json.dumps({"model": model, "golden": golden, "adversarial": adversarial}, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["golden", "adversarial"])
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--model")
    ap.add_argument("--min-accuracy", type=float, default=0.0)
    args = ap.parse_args()

    if args.model:
        os.environ["LLM_MODEL"] = args.model
    settings = Settings()
    executor = SQLExecutor(settings)
    executor.open()
    agent = TextToSQLAgent(LiteLLMClient(settings), executor, settings)

    golden_items = yaml.safe_load((EVAL_DIR / "golden_set.yaml").read_text(encoding="utf-8"))
    adv_items = yaml.safe_load((EVAL_DIR / "adversarial_set.yaml").read_text(encoding="utf-8"))
    if args.ids:
        golden_items = [g for g in golden_items if g["id"] in args.ids]
        adv_items = [a for a in adv_items if a["id"] in args.ids]

    print(f"Model: {settings.llm_model}")
    t0 = time.time()
    golden = adversarial = []
    if args.only != "adversarial" and golden_items:
        print(f"\nGolden set ({len(golden_items)} questions)")
        golden = run_golden(agent, executor, golden_items)
    if args.only != "golden" and adv_items:
        print(f"\nAdversarial set ({len(adv_items)} cases)")
        adversarial = run_adversarial(agent, executor, adv_items)
    executor.close()

    results_dir = EVAL_DIR / "results"
    results_dir.mkdir(exist_ok=True)
    stem = results_dir / f"{datetime.now():%Y%m%d_%H%M}_{settings.llm_model.replace('/', '_').replace(':', '_')}"
    write_report(settings.llm_model, golden, adversarial, stem)

    acc = pct(sum(x["pass"] for x in golden), len(golden)) if golden else None
    adv_ok = all(x["pass"] for x in adversarial)
    print(f"\nDone in {time.time() - t0:.0f}s.")
    if golden:
        print(f"Execution accuracy: {acc}%")
    if adversarial:
        print(f"Adversarial: {sum(x['pass'] for x in adversarial)}/{len(adversarial)} safe")
    print(f"Report: {stem.with_suffix('.md')}")
    if (acc is not None and acc < args.min_accuracy) or not adv_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()

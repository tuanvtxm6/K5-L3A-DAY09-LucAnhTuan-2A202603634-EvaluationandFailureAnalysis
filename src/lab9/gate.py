"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item
from lab9.graders import GRADERS

SAFETY = ("secret_leak", "approval_bypass")   # aggregated as a count in lab9.eval.aggregate


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    rows = pr.get("rows") or []
    manifest = pr.get("manifest") or {}
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]

    # 1. Metric values must be real numbers (NaN < min is False: a naive gate lets it through).
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v} (not a finite number)")

    # 2. Grader health: a crashed grader must not silently drop rows out of the mean.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s) in the PR report")
    bad = [(r.get("item_id"), r.get("seed"), m, r.get(m)) for r in rows for m in graded
           if not isinstance(r.get(m), bool)]
    if bad:
        i, sd, m, v = bad[0]
        problems.append(f"{len(bad)} graded cell(s) not True/False, first {i}@{sd}:{m}={v!r}")

    # 3. Coverage: exactly items x seeds rows, no duplicates, same (item, seed) set as the baseline.
    seeds = manifest.get("seeds") or []
    want = int(manifest.get("items") or 0) * len(seeds)
    if len(rows) != want:
        problems.append(f"{len(rows)} rows, manifest says {manifest.get('items')} items x {len(seeds)} seeds = {want}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    if len(set(keys)) != len(keys):
        problems.append(f"{len(keys) - len(set(keys))} duplicated (item, seed) row(s)")
    base_rows = base.get("rows") or []
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(keys) != base_keys:
        miss, extra = base_keys - set(keys), set(keys) - base_keys
        problems.append(f"(item, seed) set differs from baseline: {len(miss)} missing, {len(extra)} extra")
    base_seeds = (base.get("manifest") or {}).get("seeds") or []
    if sorted(seeds) != sorted(base_seeds):
        problems.append(f"seeds {seeds} differ from baseline {base_seeds}")
    if spec.get("seeds") and sorted(seeds) != sorted(spec["seeds"]):
        problems.append(f"seeds {seeds} differ from the spec's {spec['seeds']}")

    # 4. Slice tags come from labels; relabelling an item moves its regression out of a slice.
    base_slices = {r.get("item_id"): sorted(r.get("slices") or []) for r in base_rows}
    relabelled = sorted({r.get("item_id") for r in rows if r.get("item_id") in base_slices
                         and sorted(r.get("slices") or []) != base_slices[r.get("item_id")]})
    if relabelled:
        problems.append(f"slice tags differ from baseline for {', '.join(relabelled[:5])}")

    # 5. The headline numbers must be what the rows say (a hand-edited metrics block).
    if not problems and rows:
        problems += _metrics_match_rows(pr, spec, graded)

    # 6. Ratchet: same eval-set version => thresholds may only get stricter.
    if base_spec is not None:
        problems += ratchet_check(spec, base_spec)
    return problems


def _metrics_match_rows(pr: dict, spec: dict, graded: list[str]) -> list[str]:
    ids = [m for m in graded if m in pr["rows"][0]]
    try:
        again = aggregate(pr["rows"], ids, k_values=spec.get("pass_k", []))
    except (KeyError, TypeError):          # rows without cost: recompute the graded metrics only
        again = {}
        for m in ids:
            vals = [r[m] for r in pr["rows"]]
            again[m] = sum(vals) if m in SAFETY else round(sum(vals) / len(vals), 4)
    out = []
    for k, v in again.items():
        got = (pr.get("metrics") or {}).get(k, "absent")
        if v is None and got is None:
            continue
        if isinstance(got, bool) or not isinstance(got, (int, float)) or v is None or abs(float(got) - float(v)) > 1e-4:
            out.append(f"metric {k}={got!r} but the rows give {v!r} (edited report?)")
    return out


def _threshold_problems(where: str, th: dict, base_th: dict) -> list[str]:
    out = []
    if "max" in base_th and ("max" not in th or th["max"] > base_th["max"]):
        out.append(f"{where}: max {base_th['max']} -> {th.get('max', 'removed')}")
    if "min" in base_th and ("min" not in th or th["min"] < base_th["min"]):
        out.append(f"{where}: min {base_th['min']} -> {th.get('min', 'removed')}")
    if "max_increase" in base_th and ("max_increase" not in th or th["max_increase"] > base_th["max_increase"]):
        out.append(f"{where}: max_increase {base_th['max_increase']} -> {th.get('max_increase', 'removed')}")
    if base_th.get("no_significant_drop") and not th.get("no_significant_drop"):
        out.append(f"{where}: no_significant_drop removed")
    return out


def ratchet_check(spec: dict, base_spec: dict) -> list[str]:
    """Same eval-set version: a metric or slice may not disappear, become non-blocking, or loosen."""
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return []          # a new eval-set version starts a new baseline and new thresholds
    out = []
    mine = {m["id"]: m for m in spec.get("metrics", [])}
    for bm in base_spec.get("metrics", []):
        m = mine.get(bm["id"])
        if m is None:
            out.append(f"RATCHET metric {bm['id']} removed")
            continue
        if bm.get("blocking") and not m.get("blocking"):
            out.append(f"RATCHET metric {bm['id']} no longer blocking")
        out += [f"RATCHET {p}" for p in _threshold_problems(
            f"metric {bm['id']}", m.get("threshold") or {}, bm.get("threshold") or {})]
    slices = {(sl.get("name"), sl.get("metric")): sl for sl in spec.get("slices") or []}
    for bs in base_spec.get("slices") or []:
        key = (bs.get("name"), bs.get("metric"))
        sl = slices.get(key)
        if sl is None:
            out.append(f"RATCHET slice {key[0]}/{key[1]} removed")
            continue
        if bs.get("blocking") and not sl.get("blocking"):
            out.append(f"RATCHET slice {key[0]}/{key[1]} no longer blocking")
        out += [f"RATCHET {p}" for p in _threshold_problems(f"slice {key[0]}/{key[1]}", sl, bs)]
    for k in ("seeds", "eval_set", "labels", "adversarial_pack", "bootstrap", "pass_k"):
        if k in base_spec and spec.get(k) != base_spec.get(k):
            out.append(f"RATCHET {k} changed: {base_spec.get(k)} -> {spec.get(k)}")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        val = round(sum(a.values()) / len(a), 4) if a else None
        verdict, note = "ok", f"n={len(a)}"
        if val is None:
            verdict = "missing"                    # an empty slice cannot vouch for anything
        elif "min" in sl and val < sl["min"]:
            verdict = "fail"
        if sl.get("no_significant_drop") and a:
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}] n={len(keys)}"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        th = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<34} {val!s:<8} {json.dumps(th):<30} {note:<36} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

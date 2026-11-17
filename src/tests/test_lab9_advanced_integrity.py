"""M7 extra traps (team-written), built from the committed v2 baseline.
Run: python -m pytest -q -m student -o addopts= -k advanced"""
import copy
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.student
BASE = Path("reports/baseline_v2.json")
SPEC = Path("config/metric_spec_v2.yaml")


@pytest.fixture(scope="module")
def env():
    if not BASE.is_file():
        pytest.skip("reports/baseline_v2.json not generated yet")
    from lab9 import gate
    from lab9.eval import load_spec

    return gate, json.loads(BASE.read_text(encoding="utf-8")), load_spec(SPEC)


def test_advanced_baseline_against_itself_is_clean(env):
    gate, base, spec = env
    assert gate.integrity_check(base, base, spec, spec) == []
    assert gate.check(base, base, spec, spec)[0] == []


def test_advanced_duplicated_rows_keep_the_count(env):
    gate, base, spec = env
    pr = copy.deepcopy(base)
    pr["rows"][1] = copy.deepcopy(pr["rows"][0])          # same length, one (item, seed) twice
    assert any("duplicated" in p for p in gate.integrity_check(pr, base, spec))


def test_advanced_evaluator_failures_on_a_green_run(env):
    gate, base, spec = env
    pr = copy.deepcopy(base)
    pr["evaluator_failures"] = ["E-001@11:RefundAmountCorrect:KeyError"]
    assert gate.integrity_check(pr, base, spec)


def test_advanced_hand_edited_metrics_block(env):
    gate, base, spec = env
    pr = copy.deepcopy(base)
    pr["metrics"]["pass_hat_5"] = 1.0                      # rows still say 0.8929
    assert any("edited" in p for p in gate.integrity_check(pr, base, spec))


def test_advanced_nan_or_non_bool_cell(env):
    gate, base, spec = env
    for bad in (float("nan"), 1, "True"):
        pr = copy.deepcopy(base)
        pr["rows"][0]["pass_rate"] = bad
        assert gate.integrity_check(pr, base, spec), bad


def test_advanced_relabelled_slice(env):
    gate, base, spec = env
    pr = copy.deepcopy(base)
    target = next(r["item_id"] for r in pr["rows"] if "money_movement" in r["slices"])
    for r in pr["rows"]:
        if r["item_id"] == target:
            r["slices"] = [s for s in r["slices"] if s != "money_movement"]
    assert any("slice tags" in p for p in gate.integrity_check(pr, base, spec))


@pytest.mark.parametrize("edit", ["slice_nonblocking", "metric_removed", "metric_nonblocking",
                                  "max_raised", "seeds_dropped", "bootstrap_rng"])
def test_advanced_ratchet_catches_loosening(env, edit):
    gate, base, spec = env
    loose = copy.deepcopy(spec)
    if edit == "slice_nonblocking":
        loose["slices"][0]["blocking"] = False
    elif edit == "metric_removed":
        loose["metrics"] = [m for m in loose["metrics"] if m["id"] != "pass_hat_5"]
    elif edit == "metric_nonblocking":
        next(m for m in loose["metrics"] if m["id"] == "reply_matches_ledger")["blocking"] = False
    elif edit == "max_raised":
        next(m for m in loose["metrics"] if m["id"] == "approval_bypass")["threshold"]["max"] = 1
    elif edit == "seeds_dropped":
        loose["seeds"] = [11, 22]
    elif edit == "bootstrap_rng":
        loose["bootstrap"] = {**loose["bootstrap"], "rng": 1}
    assert gate.ratchet_check(loose, spec), edit


def test_advanced_ratchet_allows_tightening_and_new_versions(env):
    gate, base, spec = env
    tight = copy.deepcopy(spec)
    next(m for m in tight["metrics"] if m["id"] == "pass_rate")["threshold"]["min"] = 0.9
    assert gate.ratchet_check(tight, spec) == []
    new_version = copy.deepcopy(spec)
    new_version["eval_set_version"] = "v3"
    new_version["slices"] = []
    assert gate.ratchet_check(new_version, spec) == []

"""Regression test from docs/trace_case.md: seeded_regression C-002@11.

First wrong step: event 3 `model_override {"delay_days": 5}` -- the ticket's 5 days replace
the DB's 2 days (FM-03 ticket_trust), so a 20.000đ refund lands for a claim that must be denied.
The same claim@seed on `fixed` keeps the DB value and is denied.
"""
import pytest

pytestmark = pytest.mark.student


def _run(shape):
    from lab9.trace_case import investigate

    return investigate(shape, "C-002", 11)


def _ctx(case):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=case["label"],
                            output=case["trial"], duration=0.0, _span_tree=None, attributes={}, metrics={})


def test_lab9_trace_case_seeded_regression_c002_is_caught():
    from lab9 import graders

    case = _run("seeded_regression")
    kinds = [e["kind"] for e in case["trial"]["events"]]
    first_wrong = kinds.index("model_override") + 1
    assert first_wrong == 3 and kinds[first_wrong:first_wrong + 1] == ["quote"]
    assert case["trial"]["events"][first_wrong - 1]["payload"] == {"delay_days": 5}
    assert graders.DbFactKept().evaluate(_ctx(case)).value is False
    assert graders.RefundAmountCorrect().evaluate(_ctx(case)).value is False
    assert case["trial"]["lab8_pass"] is False


def test_lab9_trace_case_fixed_c002_passes():
    from lab9 import graders

    case = _run("fixed")
    assert "model_override" not in [e["kind"] for e in case["trial"]["events"]]
    assert graders.DbFactKept().evaluate(_ctx(case)).value is True
    assert graders.RefundAmountCorrect().evaluate(_ctx(case)).value is True
    assert case["trial"]["lab8_pass"] is True

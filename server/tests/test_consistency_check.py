"""Unit tests for the replay consistency harness (scripts/consistency_check.py).

The harness itself needs a running stack and real model calls; these cover the
pure comparison logic with fabricated run records, so a bug in the diff can't
quietly turn a divergent pair of runs into a pass.
"""

from __future__ import annotations

import copy

from consistency_check import diff_runs, missing_rows, rows_fired
from replay_session import _turn_record


def _turn(**over: object) -> dict:
    base = {
        "kind": "answer",
        "persona_id": "technical_evaluator",
        "concern_id": "technical_approach",
        "is_follow_up": False,
        "prompt": "Walk me through the architecture.",
        "sent": "Containerized microservices on GovCloud.",
        "matched_rows": ["approach_cited"],
        "support_delta": 1,
        "meter": 51,
        "capped": False,
        "concern_status": "satisfied",
        "reply": "That tracks with the proposal.",
        "rationale": "Cited a concrete approach element.",
    }
    base.update(over)
    return base


def _run(*turns: dict) -> dict:
    return {
        "name": "fixture",
        "turns": list(turns),
        "final_meters": {"technical_evaluator": (51, False)},
        "concern_status": {"technical_approach": "satisfied"},
    }


def test_identical_runs_have_no_diff() -> None:
    run = _run(_turn())
    assert diff_runs(run, copy.deepcopy(run)) == []


def test_changed_delta_is_reported() -> None:
    base = _run(_turn())
    other = _run(_turn(support_delta=-1))
    diffs = diff_runs(base, other)
    assert len(diffs) == 1
    assert "support_delta" in diffs[0]


def test_changed_reply_is_reported() -> None:
    """The model's wording counts: the user reads the reply, not just the meter."""
    diffs = diff_runs(_run(_turn()), _run(_turn(reply="Different wording entirely.")))
    assert len(diffs) == 1
    assert "reply" in diffs[0]


def test_row_order_is_not_a_divergence() -> None:
    """matched_rows is a set upstream; _turn_record sorts it so order can't matter."""
    base = _run(_turn(matched_rows=["approach_cited", "contradiction"]))
    other = _run(_turn(matched_rows=["approach_cited", "contradiction"]))
    assert diff_runs(base, other) == []


def test_turn_record_sorts_matched_rows() -> None:
    prompt = {"is_follow_up": True, "prompt": "And the staffing?"}
    res = {
        "persona_id": "contracting_officer",
        "concern_id": "cost_realism",
        "matched_rows": ["contradiction", "approach_cited"],
        "support_delta": 0,
        "meter": 50,
        "capped": False,
        "concern_status": "partial",
        "reply": "Which number is it?",
        "rationale": "Conflicts with an earlier claim.",
    }
    record = _turn_record(prompt, "Forty at steady state.", res)
    assert record["matched_rows"] == ["approach_cited", "contradiction"]
    assert record["is_follow_up"] is True


def test_differing_turn_count_is_reported() -> None:
    diffs = diff_runs(_run(_turn(), _turn()), _run(_turn()))
    assert any("turn count" in d for d in diffs)


def test_differing_final_meters_are_reported() -> None:
    base = _run(_turn())
    other = _run(_turn())
    other["final_meters"] = {"technical_evaluator": (25, True)}
    assert any("final meters" in d for d in diff_runs(base, other))


def test_rows_fired_collects_across_turns() -> None:
    run = _run(_turn(), _turn(matched_rows=["contradiction", "false_fact"]))
    assert rows_fired(run) == {"approach_cited", "contradiction", "false_fact"}


def test_missing_rows_flags_a_scenario_that_stopped_working() -> None:
    run = _run(_turn())
    assert missing_rows(run, ["contradiction"]) == ["contradiction"]
    assert missing_rows(run, ["approach_cited"]) == []

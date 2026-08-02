"""Unit tests for the replay consistency harness (scripts/consistency_check.py).

The harness itself needs a running stack and real model calls; these cover the
pure comparison logic with fabricated run records, so a bug in the diff can't
quietly turn a divergent pair of runs into a pass.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
from consistency_check import (
    check_scenario,
    consistency_report,
    diff_runs,
    main,
    missing_rows,
    rows_fired,
    write_report,
)
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


def _clarification() -> dict:
    return {
        "kind": "clarify",
        "persona_id": "technical_evaluator",
        "concern_id": "technical_approach",
        "sent": "Could you clarify the staffing assumption?",
        "reply": "The baseline assumes three named leads.",
        "remaining": 1,
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


def test_check_scenario_prints_score_summaries_and_score_divergence(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = iter(
        [
            _run(_clarification(), _turn()),
            _run(
                _clarification(),
                _turn(
                    support_delta=-1,
                    meter=49,
                    reply="Different wording entirely.",
                )
            ),
        ]
    )
    monkeypatch.setattr("consistency_check.replay", lambda *_args: next(runs))

    assert not check_scenario(
        "http://api.example",
        {"name": "fixture"},
        runs=2,
        quiet=True,
        reset_cmd=None,
        expect_rows=[],
    )

    output = capsys.readouterr().out
    assert "score summary:" in output
    assert "run 1: technical_approach rows=approach_cited delta=+1 meter=51 capped=False" in output
    assert "run 2: technical_approach rows=approach_cited delta=-1 meter=49 capped=False" in output
    assert "SCORE DIVERGED: support_delta, meter" in output
    assert 'final_meters={"technical_evaluator": [51, false]}' in output
    assert "reply" in output


def test_consistency_report_records_each_scored_turn_and_score_divergence() -> None:
    report = consistency_report(
        "fixture",
        [
            _run(_clarification(), _turn()),
            _run(
                _clarification(),
                _turn(support_delta=-1, meter=49, reply="Different wording entirely."),
            ),
        ],
    )

    assert report["runs"] == [
        {
            "run": 1,
            "score_turns": [
                {
                    "turn": 2,
                    "concern_id": "technical_approach",
                    "matched_rows": ["approach_cited"],
                    "support_delta": 1,
                    "meter": 51,
                    "capped": False,
                    "concern_status": "satisfied",
                }
            ],
            "final_meters": {"technical_evaluator": (51, False)},
        },
        {
            "run": 2,
            "score_turns": [
                {
                    "turn": 2,
                    "concern_id": "technical_approach",
                    "matched_rows": ["approach_cited"],
                    "support_delta": -1,
                    "meter": 49,
                    "capped": False,
                    "concern_status": "satisfied",
                }
            ],
            "final_meters": {"technical_evaluator": (51, False)},
        },
    ]
    assert report["comparisons"] == [
        {
            "run": 2,
            "differences": report["comparisons"][0]["differences"],
            "score_differences": ["support_delta", "meter"],
        }
    ]
    assert any(
        difference["field"] == "reply"
        for difference in report["comparisons"][0]["differences"]
    )


def test_consistency_report_keeps_complete_difference_values_and_outcome() -> None:
    original = "a" * 300
    changed = "b" * 300
    report = consistency_report(
        "fixture",
        [_run(_turn(reply=original)), _run(_turn(reply=changed))],
        expected_rows=["contradiction"],
        missing_expected_rows=["contradiction"],
        passed=False,
        scenario_path="scripts/replay/scenario-fixture.json",
    )

    reply_difference = next(
        difference
        for difference in report["comparisons"][0]["differences"]
        if difference["field"] == "reply"
    )
    assert reply_difference["run_1"] == original
    assert reply_difference["this"] == changed
    assert report["passed"] is False
    assert report["expected_rows"] == ["contradiction"]
    assert report["missing_expected_rows"] == ["contradiction"]
    assert report["scenario_path"] == "scripts/replay/scenario-fixture.json"


def test_write_report_saves_json_under_requested_directory(tmp_path: Path) -> None:
    path = write_report(
        {"scenarios": [{"name": "fixture", "runs": []}]}, report_dir=tmp_path
    )

    assert path.parent == tmp_path
    assert path.suffix == ".json"
    assert json.loads(path.read_text()) == {"scenarios": [{"name": "fixture", "runs": []}]}


def test_main_saves_invocation_metadata_when_a_scenario_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scenario = tmp_path / "scenario.json"
    scenario.write_text("{}")
    captured: dict = {}

    monkeypatch.setattr("consistency_check._get", lambda *_args: {})
    monkeypatch.setattr("consistency_check._resolve", lambda _args: [str(scenario)])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "consistency_check.py",
            "--report",
            "--no-cache",
            "--expect-row",
            "contradiction",
        ],
    )

    def fake_check_scenario(*_args: object, **kwargs: object) -> bool:
        report_scenarios = kwargs["report_scenarios"]
        assert isinstance(report_scenarios, list)
        report_scenarios.append({"name": "fixture", "passed": False})
        return False

    def fake_write_report(report: dict) -> Path:
        captured.update(report)
        return tmp_path / "report.json"

    monkeypatch.setattr("consistency_check.check_scenario", fake_check_scenario)
    monkeypatch.setattr("consistency_check.write_report", fake_write_report)

    assert main() == 1
    assert captured["passed"] is False
    assert captured["invocation"] == {
        "base_url": "http://localhost:8000",
        "expect_rows": ["contradiction"],
        "no_cache": True,
        "reset_cmd": (
            "docker compose exec -T postgres psql -U airtight -d airtight "
            '-c "TRUNCATE model_response_cache"'
        ),
        "runs": 2,
        "scenarios": [str(scenario)],
    }


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

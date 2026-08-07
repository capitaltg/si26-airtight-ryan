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
    _score_differences,
    _score_summary,
    check_scenario,
    compare_baseline,
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
        "row_counts": {"approach_cited": 1},
        "support_delta": 1,
        "raw_support_delta": 1,
        "integrity_ceiling": False,
        "limit": None,
        "meter": 51,
        "capped": False,
        "concern_status": "satisfied",
        "reply": "That tracks with the proposal.",
        "rationale": "Cited a concrete approach element.",
    }
    base.update(over)
    return base


def _limit(**over: object) -> dict:
    """An over-limit measurement as the API returns it on a long answer."""
    limit = {
        "kind": "text_words",
        "measured": 240.0,
        "warning_threshold": 150.0,
        "limit_threshold": 200.0,
        "exceeded": True,
        "penalty_applied": True,
        "penalty_value": -1,
    }
    limit.update(over)
    return limit


def _run(*turns: dict) -> dict:
    return {
        "name": "fixture",
        "turns": list(turns),
        "final_meters": {"technical_evaluator": (51, False)},
        "concern_status": {"technical_approach": "satisfied"},
    }


def _clarification(**over: object) -> dict:
    clarification = {
        "kind": "clarify",
        "persona_id": "technical_evaluator",
        "concern_id": "technical_approach",
        "sent": "Could you clarify the staffing assumption?",
        "reply": "The baseline assumes three named leads.",
        "remaining": 1,
    }
    clarification.update(over)
    return clarification


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


def test_compare_baseline_reports_score_and_reaction_differences(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = _run(_turn())
    customized = _run(_turn(support_delta=-1, meter=49, reply="Different voice."))
    monkeypatch.setattr("consistency_check.replay", lambda *_args: baseline)
    monkeypatch.setattr(
        "consistency_check.replay_with_personas", lambda *_args: customized
    )
    monkeypatch.setattr(
        "consistency_check._persona_snapshots",
        lambda *_args, **_kwargs: {"technical_evaluator": {}},
    )
    monkeypatch.setattr("consistency_check._post", lambda *_args: {})
    monkeypatch.setattr("consistency_check._restore_personas", lambda *_args, **_kwargs: None)

    assert compare_baseline(
        "http://api.example",
        {"name": "fixture", "personas": {"technical_evaluator": {}}},
        quiet=True,
    )

    output = capsys.readouterr().out
    assert "baseline score:" in output
    assert "customized score:" in output
    assert "SCORE CHANGED: support_delta, meter" in output
    assert "reply" in output


def test_compare_baseline_succeeds_when_results_match(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _run(_turn())
    monkeypatch.setattr("consistency_check.replay", lambda *_args: run)
    monkeypatch.setattr("consistency_check.replay_with_personas", lambda *_args: run)
    monkeypatch.setattr(
        "consistency_check._persona_snapshots",
        lambda *_args, **_kwargs: {"technical_evaluator": {}},
    )
    monkeypatch.setattr("consistency_check._post", lambda *_args: {})
    monkeypatch.setattr("consistency_check._restore_personas", lambda *_args, **_kwargs: None)

    assert compare_baseline(
        "http://api.example",
        {"name": "fixture", "personas": {"technical_evaluator": {}}},
        quiet=True,
    )

    assert "no scoring or reaction differences" in capsys.readouterr().out


def test_compare_baseline_aligns_later_concerns_after_one_sided_followup(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A custom-only follow-up must not be compared with the next concern."""
    baseline = _run(
        _turn(),
        _turn(
            persona_id="contracting_officer",
            concern_id="cost_realism",
            prompt="Explain the price basis.",
            sent="Firm-fixed pricing for planned work.",
        ),
    )
    customized = _run(
        _turn(),
        _turn(
            is_follow_up=True,
            prompt="Name the validation control.",
            sent="We use our standard migration playbook.",
        ),
        _turn(
            persona_id="contracting_officer",
            concern_id="cost_realism",
            prompt="Explain the price basis.",
            sent="Firm-fixed pricing for planned work.",
        ),
    )
    reports: list[dict] = []
    monkeypatch.setattr("consistency_check.replay", lambda *_args: baseline)
    monkeypatch.setattr(
        "consistency_check.replay_with_personas", lambda *_args: customized
    )
    monkeypatch.setattr(
        "consistency_check._persona_snapshots",
        lambda *_args, **_kwargs: {"technical_evaluator": {}},
    )
    monkeypatch.setattr("consistency_check._post", lambda *_args: {})
    monkeypatch.setattr(
        "consistency_check._restore_personas", lambda *_args, **_kwargs: None
    )

    assert compare_baseline(
        "http://api.example",
        {"name": "fixture", "personas": {"technical_evaluator": {}}},
        quiet=True,
        report_scenarios=reports,
    )

    differences = reports[0]["comparisons"][0]["differences"]
    assert differences == [
        {
            "scope": "turn",
            "concern_id": "technical_approach",
            "attempt": "follow-up",
            "field": "added_turn",
            "run_1": None,
            "this": customized["turns"][1],
        }
    ]
    output = capsys.readouterr().out
    assert "added turn: technical_approach follow-up" in output
    assert "turn 2 (cost_realism)" not in output


def test_compare_baseline_keeps_each_same_concern_clarification_occurrence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later clarification must not overwrite an earlier one in alignment."""
    baseline = _run(
        _clarification(reply="First baseline clarification."),
        _clarification(
            sent="Could you clarify the transition timing?",
            reply="Second clarification is unchanged.",
        ),
        _turn(),
    )
    customized = _run(
        _clarification(reply="First customized clarification."),
        _clarification(
            sent="Could you clarify the transition timing?",
            reply="Second clarification is unchanged.",
        ),
        _turn(),
    )
    reports: list[dict] = []
    monkeypatch.setattr("consistency_check.replay", lambda *_args: baseline)
    monkeypatch.setattr(
        "consistency_check.replay_with_personas", lambda *_args: customized
    )
    monkeypatch.setattr(
        "consistency_check._persona_snapshots",
        lambda *_args, **_kwargs: {"technical_evaluator": {}},
    )
    monkeypatch.setattr("consistency_check._post", lambda *_args: {})
    monkeypatch.setattr(
        "consistency_check._restore_personas", lambda *_args, **_kwargs: None
    )

    assert compare_baseline(
        "http://api.example",
        {"name": "fixture", "personas": {"technical_evaluator": {}}},
        quiet=True,
        report_scenarios=reports,
    )

    assert reports[0]["comparisons"][0]["differences"] == [
        {
            "scope": "turn",
            "concern_id": "technical_approach",
            "attempt": "clarify 1",
            "field": "reply",
            "run_1": "First baseline clarification.",
            "this": "First customized clarification.",
        }
    ]


def test_compare_baseline_requires_nonempty_personas_mapping() -> None:
    with pytest.raises(ValueError, match="requires a nonempty personas object"):
        compare_baseline(
            "http://api.example",
            {"name": "fixture", "personas": {}},
            quiet=True,
        )


def test_compare_baseline_resets_target_to_shipped_default_then_restores_live_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both comparison runs start from defaults; pre-comparison live state returns."""
    live = {
        "id": "technical_evaluator",
        "display_name": "Live Dana",
        "exemplars": [
            {
                "persona": "technical_evaluator",
                "user": "existing",
                "support_delta": 1,
                "note": "keep",
            }
        ],
    }
    state = {"display_name": "Live Dana"}
    calls: list[tuple[str, str, dict | None]] = []
    baseline = _run(_turn())
    customized = _run(_turn(reply="Custom reaction."))

    monkeypatch.setattr("consistency_check._get", lambda *_args: [live])

    def post(_base: str, path: str, body: dict | None) -> dict:
        calls.append(("POST", path, body))
        state["display_name"] = "Dana"
        return {"display_name": "Dana"}

    def put(_base: str, path: str, body: dict) -> dict:
        calls.append(("PUT", path, body))
        state["display_name"] = body["display_name"]
        return body

    def replay(_base: str, scenario: dict, _quiet: bool, _report: bool) -> dict:
        assert state["display_name"] == "Dana"
        assert "personas" not in scenario
        return baseline

    def replay_customized(
        _base: str, scenario: dict, _quiet: bool, _report: bool
    ) -> dict:
        assert state["display_name"] == "Dana"
        assert set(scenario["personas"]) == {"technical_evaluator"}
        return customized

    monkeypatch.setattr("consistency_check._post", post)
    monkeypatch.setattr("consistency_check._put", put)
    monkeypatch.setattr("consistency_check.replay", replay)
    monkeypatch.setattr("consistency_check.replay_with_personas", replay_customized)

    assert compare_baseline(
        "http://api",
        {"name": "fixture", "personas": {"technical_evaluator": {"display_name": "Mara"}}},
        quiet=True,
    )

    assert calls[0] == (
        "POST",
        "/content/personas/technical_evaluator/reset",
        None,
    )
    assert calls[-1] == (
        "PUT",
        "/content/personas/technical_evaluator",
        {
            "display_name": "Live Dana",
            "exemplars": [{"user": "existing", "support_delta": 1, "note": "keep"}],
        },
    )
    assert state["display_name"] == "Live Dana"


def test_compare_baseline_restores_all_live_snapshots_when_reset_response_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reset response failure cannot strand any targeted persona at defaults."""
    live = [
        {"id": "technical_evaluator", "display_name": "Live Dana"},
        {"id": "contracting_officer", "display_name": "Live Marcus"},
    ]
    restored: list[tuple[str, dict]] = []
    monkeypatch.setattr("consistency_check._get", lambda *_args: live)
    monkeypatch.setattr(
        "consistency_check._post",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("reset response lost")),
    )
    monkeypatch.setattr(
        "consistency_check._put",
        lambda _base, path, body: restored.append((path, body)) or body,
    )
    monkeypatch.setattr(
        "consistency_check.replay",
        lambda *_args: pytest.fail("baseline must not start after reset failure"),
    )

    with pytest.raises(RuntimeError, match="reset response lost"):
        compare_baseline(
            "http://api",
            {
                "name": "fixture",
                "personas": {
                    "technical_evaluator": {"display_name": "Mara"},
                    "contracting_officer": {"display_name": "Elias"},
                },
            },
            quiet=True,
        )

    assert restored == [
        ("/content/personas/contracting_officer", {"display_name": "Live Marcus", "exemplars": []}),
        ("/content/personas/technical_evaluator", {"display_name": "Live Dana", "exemplars": []}),
    ]


def test_check_scenario_prints_score_summaries_and_score_divergence(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = iter(
        [
            _run(_clarification(), _turn()),
            _run(
                _clarification(),
                # The raw sum moves with the delta: a run that scored the same
                # rows differently diverged on the arithmetic too, and a fixture
                # that changed only the persisted number would describe a turn
                # the engine cannot produce.
                _turn(
                    support_delta=-1,
                    raw_support_delta=-1,
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
    assert "SCORE DIVERGED: support_delta, raw_support_delta, meter" in output
    assert 'final_meters={"technical_evaluator": [51, false]}' in output
    assert "reply" in output


def test_consistency_report_records_each_scored_turn_and_score_divergence() -> None:
    report = consistency_report(
        "fixture",
        [
            _run(_clarification(), _turn()),
            _run(
                _clarification(),
                _turn(
                    support_delta=-1,
                    raw_support_delta=-1,
                    meter=49,
                    reply="Different wording entirely.",
                ),
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
                    "row_counts": {"approach_cited": 1},
                    "support_delta": 1,
                    "raw_support_delta": 1,
                    "integrity_ceiling": False,
                    "limit": None,
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
                    "row_counts": {"approach_cited": 1},
                    "support_delta": -1,
                    "raw_support_delta": -1,
                    "integrity_ceiling": False,
                    "limit": None,
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
            "score_differences": ["support_delta", "raw_support_delta", "meter"],
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
        "compare_baseline": False,
        "expect_rows": ["contradiction"],
        "no_cache": True,
        "reset_cmd": (
            "docker compose exec -T postgres psql -U airtight -d airtight "
            '-c "TRUNCATE model_response_cache"'
        ),
        "runs": 2,
        "scenarios": [str(scenario)],
    }


@pytest.mark.parametrize(
    ("scenario_body", "case"),
    [
        ({}, "missing"),
        ({"personas": None}, "null"),
        ({"personas": ["technical_evaluator"]}, "non-mapping"),
        ({"personas": {}}, "empty"),
    ],
)
def test_main_compare_baseline_rejects_invalid_personas(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario_body: dict[str, object],
    case: str,
) -> None:
    scenario = tmp_path / f"scenario-{case}.json"
    scenario.write_text(json.dumps(scenario_body))
    monkeypatch.setattr("consistency_check._get", lambda *_args: {})
    monkeypatch.setattr("consistency_check._resolve", lambda _args: [str(scenario)])
    monkeypatch.setattr(
        sys,
        "argv",
        ["consistency_check.py", "--compare-baseline"],
    )

    with pytest.raises(
        SystemExit, match="--compare-baseline requires a nonempty personas object"
    ):
        main()


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--compare-baseline", "--no-cache"], "does not support --no-cache"),
        (["--compare-baseline", "--runs", "3"], "omit --runs"),
    ],
)
def test_main_compare_baseline_rejects_incompatible_flags(
    monkeypatch: pytest.MonkeyPatch, args: list[str], message: str
) -> None:
    monkeypatch.setattr(sys, "argv", ["consistency_check.py", *args])

    with pytest.raises(SystemExit, match=message):
        main()


def test_main_compare_baseline_records_invocation_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scenario = tmp_path / "scenario.json"
    scenario.write_text(
        json.dumps(
            {
                "name": "fixture",
                "personas": {"technical_evaluator": {"display_name": "Mara"}},
            }
        )
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr("consistency_check._get", lambda *_args: {})
    monkeypatch.setattr("consistency_check._resolve", lambda _args: [str(scenario)])
    monkeypatch.setattr(sys, "argv", ["consistency_check.py", "--compare-baseline", "--report"])
    monkeypatch.setattr("consistency_check.compare_baseline", lambda *_args: True)
    monkeypatch.setattr(
        "consistency_check.write_report",
        lambda report: captured.update(report) or tmp_path / "report.json",
    )

    assert main() == 0
    assert captured["invocation"] == {
        "base_url": "http://localhost:8000",
        "compare_baseline": True,
        "expect_rows": [],
        "no_cache": False,
        "reset_cmd": None,
        "runs": 2,
        "scenarios": [str(scenario)],
    }


def test_main_uses_comparison_specific_success_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scenario = tmp_path / "scenario.json"
    scenario.write_text(
        json.dumps({"personas": {"technical_evaluator": {"display_name": "Mara"}}})
    )
    monkeypatch.setattr("consistency_check._get", lambda *_args: {})
    monkeypatch.setattr("consistency_check._resolve", lambda _args: [str(scenario)])
    monkeypatch.setattr("consistency_check.compare_baseline", lambda *_args: True)
    monkeypatch.setattr(sys, "argv", ["consistency_check.py", "--compare-baseline"])

    assert main() == 0
    output = capsys.readouterr().out
    assert "PASS: every baseline comparison completed" in output
    assert "reproduced identically" not in output


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


def test_format_rows_shows_the_application_count() -> None:
    from replay_session import _format_rows

    assert _format_rows(["false_fact", "dodge"], {"false_fact": 2, "dodge": 1}) == (
        "false_fact x2, dodge"
    )
    assert _format_rows(["dodge"], {}) == "dodge"
    assert _format_rows([], {}) == "(none)"


def test_score_summary_shows_counts_and_the_clamp() -> None:
    run = _run(
        _turn(
            matched_rows=["dodge", "false_fact"],
            row_counts={"dodge": 1, "false_fact": 3},
            support_delta=-2,
            raw_support_delta=-5,
        )
    )
    summary = _score_summary(run)
    assert "false_fact x3" in summary
    assert "clamped from -5" in summary


def test_score_summary_names_the_integrity_ceiling() -> None:
    """A ceilinged turn stays inside [-2, +2], so the old clamp note never fired.

    evidence_backed (+2) with one false_fact (-1) sums to +1 and is held to 0 by
    the rubric v4 ceiling. Reporting a bare `delta=+0` there hides the whole
    reason the row exists.
    """
    run = _run(
        _turn(
            matched_rows=["false_fact", "evidence_backed"],
            row_counts={"false_fact": 1, "evidence_backed": 1},
            support_delta=0,
            raw_support_delta=1,
            integrity_ceiling=True,
        )
    )
    summary = _score_summary(run)
    assert "held to +0 by the integrity ceiling" in summary
    assert "clamped" not in summary


def test_score_summary_names_the_over_limit_penalty() -> None:
    run = _run(_turn(support_delta=0, raw_support_delta=1, limit=_limit()))
    summary = _score_summary(run)
    assert "over_limit -1" in summary
    assert "240 > 200 text_words" in summary
    # The penalty, not the ceiling, explains the drop from the raw sum.
    assert "integrity ceiling" not in summary


def test_turn_record_carries_the_limit_and_derives_the_ceiling() -> None:
    """The API never returns `integrity_ceiling`; the runner reconstructs it.

    Both reductions are in play here: the rows sum to +1, the ceiling holds that
    to 0, and the over-limit penalty then takes the persisted delta to -1.
    """
    prompt = {"is_follow_up": False, "prompt": "How many records?"}
    res = {
        "persona_id": "technical_evaluator",
        "concern_id": "technical_approach",
        "matched_rows": ["evidence_backed", "false_fact"],
        "row_counts": {"evidence_backed": 1, "false_fact": 1},
        "raw_support_delta": 1,
        "support_delta": -1,
        "limit": _limit(),
        "meter": 49,
        "capped": False,
        "concern_status": "partial",
        "reply": "That number is not what the PWS says.",
        "rationale": "One refuted count against documented staffing.",
    }
    record = _turn_record(prompt, "Twelve million records, and here is the crew.", res)
    assert record["limit"] == _limit()
    assert record["integrity_ceiling"] is True


def test_turn_record_reports_no_ceiling_when_the_clamp_explains_the_drop() -> None:
    prompt = {"is_follow_up": False, "prompt": "How many records?"}
    res = {
        "persona_id": "technical_evaluator",
        "concern_id": "technical_approach",
        "matched_rows": ["dodge", "false_fact"],
        "row_counts": {"dodge": 1, "false_fact": 3},
        "raw_support_delta": -5,
        "support_delta": -2,
        "limit": None,
        "meter": 45,
        "capped": False,
        "concern_status": "dodged",
        "reply": "That is not an answer.",
        "rationale": "Dodged, with three refuted counts.",
    }
    record = _turn_record(prompt, "Hard to say.", res)
    assert record["integrity_ceiling"] is False


def test_limit_change_is_a_score_divergence() -> None:
    """Same rows, same delta, different measurement — still not reproducible."""
    base = _run(_turn(support_delta=0, raw_support_delta=1, limit=_limit()))
    other = _run(
        _turn(support_delta=0, raw_support_delta=1, limit=_limit(measured=260.0))
    )
    assert any("limit" in d for d in _score_differences(base, other))


def test_integrity_ceiling_change_is_a_score_divergence() -> None:
    base = _run(_turn(support_delta=0, raw_support_delta=1, integrity_ceiling=True))
    other = _run(_turn(support_delta=0, raw_support_delta=0, integrity_ceiling=False))
    assert any("integrity_ceiling" in d for d in _score_differences(base, other))


def test_report_records_the_ceiling_and_the_limit() -> None:
    run = _run(
        _turn(support_delta=-1, raw_support_delta=1, integrity_ceiling=True, limit=_limit())
    )
    turn = consistency_report("fixture", [run])["runs"][0]["score_turns"][0]
    assert turn["integrity_ceiling"] is True
    assert turn["limit"] == _limit()


def test_turn_record_persists_counts_and_the_raw_delta() -> None:
    prompt = {"is_follow_up": False, "prompt": "And the records?"}
    res = {
        "persona_id": "technical_evaluator",
        "concern_id": "technical_approach",
        "matched_rows": ["false_fact", "dodge"],
        "row_counts": {"false_fact": 2, "dodge": 1},
        "raw_support_delta": -4,
        "support_delta": -2,
        "meter": 48,
        "capped": False,
        "concern_status": "dodged",
        "reply": "Which number is it?",
        "rationale": "Two refuted counts.",
    }
    record = _turn_record(prompt, "Twelve million records.", res)
    assert record["row_counts"] == {"dodge": 1, "false_fact": 2}
    assert record["raw_support_delta"] == -4


def test_application_count_change_is_a_score_divergence() -> None:
    base = _run(_turn(row_counts={"false_fact": 2}))
    other = _run(_turn(row_counts={"false_fact": 3}))
    assert any("row_counts" in d for d in _score_differences(base, other))


def test_report_records_counts_and_the_raw_delta() -> None:
    run = _run(_turn(row_counts={"false_fact": 2}, raw_support_delta=-4))
    report = consistency_report("fixture", [run])
    turn = report["runs"][0]["score_turns"][0]
    assert turn["row_counts"] == {"false_fact": 2}
    assert turn["raw_support_delta"] == -4


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

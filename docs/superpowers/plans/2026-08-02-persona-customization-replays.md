# Persona Customization Replays Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three repeatable session fixtures that temporarily customize an evaluator, run a full rehearsal, and restore the prior personas.

**Architecture:** `scripts/replay_session.py` gains an optional top-level `personas` scenario field. It snapshots each targeted persona through the content API, sends only editable fields to the existing `PUT` endpoint, runs the normal replay, then restores every snapshot in `finally`. Baseline comparison snapshots the live targeted personas, resets those IDs through the content API, runs the same answers against shipped defaults and temporary overrides, then restores the live snapshots. Three JSON files exercise Dana, Marcus, and Priya without changing fixed IDs, priorities, or rubric version.

**Tech Stack:** Python standard-library HTTP client, existing FastAPI persona API, pytest.

## Global Constraints

- Existing scenarios without `personas` behave exactly as before.
- A scenario with no `personas` calls `replay(...)` directly and does not call
  the persona content API.
- Never send `id`, `priorities`, `rubric_version`, `is_customized`, or exemplar `persona` in an update request.
- When a scenario omits `exemplars`, retain every exemplar from the snapshot in
  the apply payload. The API's omitted-field default is an empty list.
- Register a snapshot for restoration before its apply `PUT`, since the server
  may save successfully even when the client cannot read the response.
- Restore every successfully customized persona when replay succeeds or fails.
- Attempt every restore even after an earlier restore fails. On a successful
  replay, surface restoration failure. On a failed replay, preserve the original
  failure and attach restoration failures as notes.
- Persona customization is global while the replay runs. Do not use these scenarios under a concurrent runner.
- Do not add an in-process concurrency guard. The runner documents the operator
  restriction because separate processes cannot share an in-process lock.
- The runner remains a pure HTTP client. It never opens persona markdown files or changes scoring code.
- New files require the `AGENTS.md` structure block update.

---

### Task 1: Add temporary persona customization to the replay runner

**Files:**
- Modify: `scripts/replay_session.py`
- Create: `server/tests/test_replay_session.py`

**Interfaces:**
- Consumes: `GET /content/personas`, `PUT /content/personas/{id}`, and existing `replay(base_url, scenario, quiet, want_report)`.
- Produces: `replay_with_personas(base_url, scenario, quiet, want_report) -> dict`.

- [ ] **Step 1: Write failing tests**

```python
def test_persona_update_omits_locked_and_server_owned_fields() -> None:
    from replay_session import persona_update

    update = persona_update(
        {
            "id": "technical_evaluator",
            "display_name": "Mara",
            "priorities": ["risk"],
            "rubric_version": 99,
            "is_customized": True,
            "exemplars": [{"persona": "technical_evaluator", "user": "x", "support_delta": 1, "note": "n"}],
        }
    )

    assert update == {
        "display_name": "Mara",
        "exemplars": [{"user": "x", "support_delta": 1, "note": "n"}],
    }


def test_replay_with_personas_restores_snapshot_when_replay_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from replay_session import replay_with_personas

    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr("replay_session._get", lambda *_: [{"id": "technical_evaluator", "display_name": "Dana", "exemplars": []}])
    monkeypatch.setattr("replay_session._put", lambda _base, path, body: calls.append((path, body)) or {})
    monkeypatch.setattr("replay_session.replay", lambda *_: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        replay_with_personas("http://api", {"personas": {"technical_evaluator": {"display_name": "Mara"}}}, True, False)

    assert calls == [
        ("/content/personas/technical_evaluator", {"display_name": "Mara"}),
        ("/content/personas/technical_evaluator", {"display_name": "Dana", "exemplars": []}),
    ]
```

- [ ] **Step 2: Verify RED**

Run: `cd server && .venv/bin/pytest tests/test_replay_session.py -v`

Expected: import failure because `persona_update` and `replay_with_personas` do not exist.

- [ ] **Step 3: Add minimal HTTP and restoration helpers**

```python
EDITABLE_PERSONA_FIELDS = (
    "display_name", "intro", "voice", "demographics", "values", "wants",
    "non_negotiables", "polly_voice_id", "exemplars",
)


def persona_update(persona: dict) -> dict:
    update = {key: persona[key] for key in EDITABLE_PERSONA_FIELDS if key in persona}
    update["exemplars"] = [
        {key: exemplar[key] for key in ("user", "support_delta", "note")}
        for exemplar in update.get("exemplars", [])
    ]
    return update


def _put(base_url: str, path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base_url}{path}", data=data, headers={"Content-Type": "application/json"}, method="PUT"
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.loads(response.read())


def replay_with_personas(base_url: str, scenario: dict, quiet: bool, want_report: bool) -> dict:
    requested = scenario.get("personas", {})
    live = {persona["id"]: persona for persona in _get(base_url, "/content/personas")}
    unknown = set(requested) - set(live)
    if unknown:
        raise ValueError(f"unknown persona customization: {sorted(unknown)}")
    originals: list[tuple[str, dict]] = []
    try:
        for persona_id, overrides in requested.items():
            original = live[persona_id]
            originals.append((persona_id, persona_update(original)))
            customized = persona_update({**original, **overrides})
            _put(base_url, f"/content/personas/{persona_id}", customized)
        return replay(base_url, scenario, quiet, want_report)
    finally:
        for persona_id, original in reversed(originals):
            _put(base_url, f"/content/personas/{persona_id}", original)
```

Make `main()` call `replay_with_personas` instead of `replay`.

- [ ] **Step 4: Verify GREEN and regressions**

Run: `cd server && .venv/bin/pytest tests/test_replay_session.py tests/test_consistency_check.py -v`

Expected: pass.

Run: `cd server && .venv/bin/ruff check . && .venv/bin/mypy app`

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add scripts/replay_session.py server/tests/test_replay_session.py
git commit -m "feat: support temporary persona customization in replays"
```

#### Task 1 review resolution: preserve baseline behavior and complete restoration

**Files:**
- Modify: `scripts/replay_session.py`
- Modify: `server/tests/test_replay_session.py`

- [ ] **Step 6: Write failing reliability tests**

```python
def test_replay_with_personas_bypasses_persona_api_without_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from replay_session import replay_with_personas

    monkeypatch.setattr(
        "replay_session._get",
        lambda *_: pytest.fail("persona API must not be called"),
    )
    sentinel = {"name": "baseline"}
    monkeypatch.setattr("replay_session.replay", lambda *_: sentinel)

    assert replay_with_personas("http://api", {"concerns": {}}, True, False) == sentinel


def test_replay_with_personas_attempts_every_restore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from replay_session import replay_with_personas

    calls: list[str] = []
    monkeypatch.setattr(
        "replay_session._get",
        lambda *_: [
            {"id": "technical_evaluator", "display_name": "Dana"},
            {"id": "contracting_officer", "display_name": "Marcus"},
        ],
    )
    def put(_base: str, path: str, _body: dict) -> dict:
        calls.append(path)
        if len(calls) == 3:
            raise RuntimeError("restore failed")
        return {}
    monkeypatch.setattr("replay_session._put", put)
    monkeypatch.setattr("replay_session.replay", lambda *_: {"name": "run"})

    with pytest.raises(RuntimeError, match="failed to restore"):
        replay_with_personas(
            "http://api",
            {"personas": {"technical_evaluator": {}, "contracting_officer": {}}},
            True,
            False,
        )

    assert calls == [
        "/content/personas/technical_evaluator",
        "/content/personas/contracting_officer",
        "/content/personas/contracting_officer",
        "/content/personas/technical_evaluator",
    ]


def test_replay_with_personas_preserves_replay_error_when_restore_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from replay_session import replay_with_personas

    calls = 0
    monkeypatch.setattr(
        "replay_session._get",
        lambda *_: [{"id": "technical_evaluator", "display_name": "Dana"}],
    )
    def put(*_args: object) -> dict:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("restore failed")
        return {}
    monkeypatch.setattr("replay_session._put", put)
    monkeypatch.setattr("replay_session.replay", lambda *_: (_ for _ in ()).throw(RuntimeError("replay failed")))

    with pytest.raises(RuntimeError, match="replay failed") as caught:
        replay_with_personas(
            "http://api",
            {"personas": {"technical_evaluator": {}}},
            True,
            False,
        )

    assert caught.value.__notes__ == ["restore failed: restore failed"]
```

- [ ] **Step 7: Verify RED**

Run: `cd server && .venv/bin/pytest tests/test_replay_session.py -v`

Expected: baseline test fails because `_get` is called; restoration test fails
because a restore error stops the loop.

- [ ] **Step 8: Implement direct baseline replay and best-effort restoration**

```python
def replay_with_personas(base_url: str, scenario: dict, quiet: bool, want_report: bool) -> dict:
    requested = scenario.get("personas", {})
    if not requested:
        return replay(base_url, scenario, quiet, want_report)
    snapshots = _persona_snapshots(base_url, requested)
    originals: list[tuple[str, dict]] = []
    original_error: Exception | None = None
    try:
        for persona_id, overrides in requested.items():
            original = snapshots[persona_id]
            customized = persona_update({**original, **overrides})
            originals.append((persona_id, original))
            _put(base_url, f"/content/personas/{persona_id}", customized)
        return replay(base_url, scenario, quiet, want_report)
    except Exception as exc:
        original_error = exc
        raise
    finally:
        restore_errors: list[Exception] = []
        for persona_id, original in reversed(originals):
            try:
                _put(base_url, f"/content/personas/{persona_id}", original)
            except Exception as exc:
                restore_errors.append(exc)
        if restore_errors:
            message = "; ".join(f"restore failed: {exc}" for exc in restore_errors)
            if original_error is not None:
                original_error.add_note(message)
            else:
                raise RuntimeError(message) from restore_errors[0]
```

- [ ] **Step 9: Verify GREEN**

Run: `cd server && .venv/bin/pytest tests/test_replay_session.py tests/test_consistency_check.py -v`

Expected: pass.

- [ ] **Step 10: Commit review resolution**

```bash
git add scripts/replay_session.py server/tests/test_replay_session.py
git commit -m "fix: restore personas reliably after replays"
```

### Task 2: Add the three customized evaluator scenarios and replay documentation

**Files:**
- Create: `scripts/replay/scenario-custom-dana.json`
- Create: `scripts/replay/scenario-custom-marcus.json`
- Create: `scripts/replay/scenario-custom-priya.json`
- Modify: `scripts/replay/README.md`
- Modify: `AGENTS.md`
- Test: `server/tests/test_replay_session.py`

**Interfaces:**
- Consumes: `replay_with_personas` and standard concern-keyed JSON format.
- Produces: three complete fixtures runnable with `python3 scripts/replay_session.py scripts/replay/scenario-custom-*.json`.

- [ ] **Step 1: Write failing fixture validation test**

```python
@pytest.mark.parametrize(
    "filename,persona_id",
    [
        ("scenario-custom-dana.json", "technical_evaluator"),
        ("scenario-custom-marcus.json", "contracting_officer"),
        ("scenario-custom-priya.json", "program_rep"),
    ],
)
def test_custom_persona_scenarios_define_one_editable_persona(
    filename: str, persona_id: str
) -> None:
    scenario = json.loads((REPLAY_DIR / filename).read_text())
    assert set(scenario["personas"]) == {persona_id}
    assert set(scenario["concerns"]) == EXPECTED_CONCERNS
    assert not {"id", "priorities", "rubric_version"} & set(scenario["personas"][persona_id])
```

- [ ] **Step 2: Verify RED**

Run: `cd server && .venv/bin/pytest tests/test_replay_session.py::test_custom_persona_scenarios_define_one_editable_persona -v`

Expected: fail because scenario files are missing.

- [ ] **Step 3: Create fixtures and document format**

Each scenario uses one `personas` mapping with a customized display name, voice,
values, wants, non-negotiables, and a three-level exemplar set. Each contains all
eight fixed concern answers. Add this README format section:

```json
"personas": {
  "technical_evaluator": {
    "display_name": "Mara",
    "voice": "Direct and architecture-first.",
    "values": ["operationally testable architecture"],
    "wants": ["named integration and migration controls"],
    "non_negotiables": ["do not trade migration safety for speed"],
    "polly_voice_id": "Ruth",
    "exemplars": [{"user": "...", "support_delta": 2, "note": "..."}]
  }
}
```

Document that the runner restores prior personas, but these fixtures must not run
concurrently with other persona-writing activity.

- [ ] **Step 4: Verify fixtures**

Run: `cd server && .venv/bin/pytest tests/test_replay_session.py -v`

Expected: pass.

Run: `python3 -m json.tool scripts/replay/scenario-custom-dana.json >/dev/null && python3 -m json.tool scripts/replay/scenario-custom-marcus.json >/dev/null && python3 -m json.tool scripts/replay/scenario-custom-priya.json >/dev/null`

Expected: all three commands exit 0.

- [ ] **Step 5: Run one live scenario when stack is available**

Run: `python3 scripts/replay_session.py scripts/replay/scenario-custom-dana.json`

Expected: full session completes; then `GET /content/personas` shows Dana restored to her pre-run value.

- [ ] **Step 6: Commit**

```bash
git add scripts/replay scripts/replay_session.py server/tests/test_replay_session.py AGENTS.md
git commit -m "test: add customized persona replay scenarios"
```

### Task 3: Compare shipped-default and customized replay results

**Files:**
- Modify: `scripts/consistency_check.py`
- Modify: `server/tests/test_consistency_check.py`
- Modify: `scripts/replay/README.md`

**Interfaces:**
- Consumes: a scenario's optional `personas` mapping and
  `replay_with_personas(base_url, scenario, quiet, want_report)`.
- Produces: `compare_baseline(base_url, scenario, quiet, report_scenarios=None,
  scenario_path=None) -> bool` and the `--compare-baseline` CLI option.

- [ ] **Step 1: Write failing comparison tests**

```python
def test_compare_baseline_reports_score_and_reaction_differences(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = _run(_turn())
    customized = _run(_turn(support_delta=-1, meter=49, reply="Different voice."))
    monkeypatch.setattr("consistency_check.replay", lambda *_args: baseline)
    monkeypatch.setattr(
        "consistency_check.replay_with_personas", lambda *_args: customized
    )

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

    assert compare_baseline(
        "http://api.example",
        {"name": "fixture", "personas": {"technical_evaluator": {}}},
        quiet=True,
    )

    assert "no scoring or reaction differences" in capsys.readouterr().out
```

- [ ] **Step 2: Verify RED**

Run: `cd server && .venv/bin/pytest tests/test_consistency_check.py -k compare_baseline -v`

Expected: import failure because `compare_baseline` does not exist.

- [ ] **Step 3: Add baseline comparison mode**

```python
from replay_session import replay, replay_with_personas


def compare_baseline(
    base_url: str,
    scenario: dict,
    quiet: bool,
    report_scenarios: list[dict[str, Any]] | None = None,
    scenario_path: str | None = None,
) -> bool:
    requested = scenario.get("personas")
    if not isinstance(requested, dict) or not requested:
        raise ValueError("baseline comparison requires a nonempty personas object")
    originals = list(_persona_snapshots(base_url, requested, get=_get).items())
    baseline_scenario = {key: value for key, value in scenario.items() if key != "personas"}
    original_error: Exception | None = None
    try:
        for persona_id in requested:
            _post(base_url, f"/content/personas/{persona_id}/reset", None)
        baseline = replay(base_url, baseline_scenario, quiet, False)
        customized = replay_with_personas(base_url, scenario, quiet, False)
    except Exception as exc:
        original_error = exc
        raise
    finally:
        _restore_personas(base_url, originals, original_error, put=_put)
    diffs = diff_runs(baseline, customized)
    score_diffs = _score_differences(baseline, customized)

    print(c(f"\\n=== baseline comparison: {scenario.get('name', '(unnamed)')} ===", "1;35"))
    print(c(f"  baseline score: {_score_summary(baseline)}", "2"))
    print(c(f"  customized score: {_score_summary(customized)}", "2"))
    if not diffs:
        print(c("  no scoring or reaction differences", "2"))
    elif score_diffs:
        print(c(f"  SCORE CHANGED: {', '.join(score_diffs)}", "33"))
    else:
        print(c("  score unchanged; reaction changed", "33"))
    if diffs:
        for diff in diffs:
            print(f"    - {diff}")
    if report_scenarios is not None:
        report = consistency_report(
            scenario.get("name", "(unnamed)"),
            [baseline, customized],
            passed=True,
            scenario_path=scenario_path,
        )
        report["comparison_mode"] = "baseline"
        report_scenarios.append(report)
    return True
```

Add `ap.add_argument("--compare-baseline", action="store_true", help="reset targeted personas to shipped defaults, then compare with temporary overrides")`. In `main()`, require a nonempty `personas` object; otherwise call `compare_baseline(...)` instead of `check_scenario(...)`. This mode always runs one shipped-default/customized pair, so reject `--runs` when it differs from the existing default `2`, and reject `--no-cache`. Include `compare_baseline` in the saved report invocation metadata and use comparison-specific final success text.

Document:

```sh
python3 scripts/consistency_check.py scripts/replay/scenario-custom-dana.json --compare-baseline
```

State that score changes are observations from different validated extraction
facts. They are not failures, and the reaction is always compared too.

- [ ] **Step 4: Verify GREEN and regressions**

Run: `cd server && .venv/bin/pytest tests/test_consistency_check.py tests/test_replay_session.py -v`

Expected: pass.

Run: `cd server && .venv/bin/ruff check . && .venv/bin/mypy app`

Expected: clean.

- [ ] **Step 5: Commit comparison mode**

```bash
git add scripts/consistency_check.py server/tests/test_consistency_check.py scripts/replay/README.md
git commit -m "feat: compare customized replays with baseline"
```

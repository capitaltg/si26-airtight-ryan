# Persona Customization Replays Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three repeatable session fixtures that temporarily customize an evaluator, run a full rehearsal, and restore the prior personas.

**Architecture:** `scripts/replay_session.py` gains an optional top-level `personas` scenario field. It snapshots each targeted persona through the content API, sends only editable fields to the existing `PUT` endpoint, runs the normal replay, then restores every snapshot in `finally`. Three JSON files exercise Dana, Marcus, and Priya without changing fixed IDs, priorities, or rubric version.

**Tech Stack:** Python standard-library HTTP client, existing FastAPI persona API, pytest.

## Global Constraints

- Existing scenarios without `personas` behave exactly as before.
- Never send `id`, `priorities`, `rubric_version`, `is_customized`, or exemplar `persona` in an update request.
- Restore every successfully customized persona when replay succeeds or fails.
- Persona customization is global while the replay runs. Do not use these scenarios under a concurrent runner.
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

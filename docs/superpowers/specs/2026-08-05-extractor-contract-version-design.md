# Extractor contract version and pin invalidation: design spec

_The extraction pin replays a stored model output whenever the key matches, but the key omits the model and the prompt contract that produced it. Add both, so a model upgrade or a prompt-semantics fix cannot silently replay pre-fix extractions, and record on every turn which path produced its extraction._

**Status:** design approved 2026-08-05.

_Issue: `docs/issues/prompt-fixes-model-upgrades.md`._

---

## 1. Problem

`extraction_key` (`server/app/pipeline/extraction_pin.py:39`) hashes the normalized answer, persona id, concern id, prior ledger, prior answers, the authored-content fingerprint, and `Extraction.model_json_schema()`. `run_extraction` checks it before the model call and returns the stored tool input on a hit (`server/app/pipeline/extraction.py:277`).

Nothing in that key describes *how* the extraction was produced. Three things are missing.

**The model is not part of pin identity.** `ExtractionPinRow.model_id` is written (`extraction_pin.py:153`) and documented as the handle for "a targeted delete" (`server/app/db/models.py:242`), but lookup never reads it. Change `settings.bedrock_model_id` (`server/app/config.py:13`, today `us.anthropic.claude-sonnet-4-5-20250929-v1:0`) and every previously seen input keeps replaying the old model's output. The upgrade only reaches inputs nobody has answered before, which is the opposite of what a model upgrade is for.

**The prompt contract is not part of pin identity.** The prompt is built in code — `build_extraction_static_prefix` and `build_extraction_dynamic_suffix` (`extraction.py:108`, `:156`) — and none of that text is hashed. That is deliberate for wording changes, and the module says so: "Rewording a hardcoded instruction no longer unpins" (`extraction_pin.py:12`). But it also means a change to what the prompt *asks the model to do* is invisible to the key.

**Those two gaps compose into a live trap.** `_render_persona` (`extraction.py:49`) emits display name, voice, demographics, values, wants, priorities, and non-negotiables. It does not emit `persona.exemplars`. Meanwhile `compute_extraction_fingerprint` (`server/app/content/loader.py:57`) hashes `p.model_dump(mode="json")` for each persona, which includes those same exemplars. So exemplars already move the pin key while reaching no prompt. Wire them into the prompt — the standing bug — and the authored content is unchanged, the schema is unchanged, the key is unchanged, and every previously seen input keeps its pre-fix extraction with no model call. The fix ships and does nothing, and no test fails.

## 2. Approach

Make the key describe the full production contract: the inputs *and* the machinery. Two new hashed fields, `extractor_contract_version` and `model_id`. Four decisions shape the rest.

**Model id is hashed, not merely recorded.** A model change becomes a pin miss automatically, with no human step to forget. The response cache keys on the model id too (`server/app/bedrock/client.py:117`), so those misses are real Bedrock calls rather than replays — that cost is the point. The `model_id` column stays, now as provenance and as the handle for a targeted delete when someone wants to reclaim rows a rollback stranded.

**The contract version is a human-set constant, not a derived hash.** Hashing the prompt-builder source would unpin everything on a comment edit, which is exactly the churn the pin exists to prevent. A constant with a stated bump rule keeps the decision where the judgment is: does this edit change what the model is asked to report, or only how the request reads.

**Post-processing stays out of the key, on purpose.** The issue lists a post-processing contract version as missing. It should stay missing. `reanchor_spans`, `drop_ungrounded`, and `compute_conciseness` run on the replay path as well as the fresh path (`extraction.py:313-325`), and `score_turn` recomputes from the stored findings, so a fix to any of them already reaches pinned rows without a model call. That is the stated design: "a later fix to those rules reaches already-pinned inputs with no model call" (`extraction_pin.py:16`). Hashing a post-processing version would force re-extraction to deliver a change that needs none. `Extraction.model_json_schema()` remains in the key and covers the one post-processing concern that does matter: a stored payload that no longer validates.

**Provenance is recorded, not yet displayed.** Each turn stores how its extraction was produced. Nothing reads the column in this spec — no report field, no API field, no UI. It exists so the question "did this turn call the model, and under which contract" has an answer in the database instead of in a log that has rotated away.

## 3. Changes

### 3.1 `server/app/pipeline/extraction_pin.py`

`extraction_key` gains two required keyword parameters and two payload entries:

```python
def extraction_key(
    *,
    answer: str,
    persona_id: str,
    concern_id: str,
    prior_claims: Sequence[ClaimLedger],
    prior_answers: Mapping[int, str],
    extraction_fingerprint: str,
    extractor_contract_version: int,
    model_id: str,
) -> str:
```

with `"extractor_contract_version": extractor_contract_version` and `"model_id": model_id` added to `payload`. Both are passed in rather than read from `settings` or imported from `extraction`, so the function stays pure, stays importable without a settings load, and stays trivially testable — and so `extraction_pin` does not import `extraction`, which imports it.

The docstring gains the exclusion list: rubric (score recomputes from findings), post-processing rules (they re-run on replay), and prompt wording that does not change what is asked (the contract version covers semantics, deliberately not bytes).

`ExtractionPin.put` gains `contract_version: int`; `NullExtractionPin`, `InMemoryExtractionPin`, and `DbExtractionPin` follow, with `DbExtractionPin` writing it to the new column.

### 3.2 `server/app/pipeline/extraction.py`

Add the constant next to the prompt builders it governs:

```python
# Identity of the extraction contract: the prompt's semantics plus the tool it
# forces. Hashed into `extraction_key`, so bumping it is how a prompt fix reaches
# inputs that are already pinned.
#
# Bump when the prompt changes what the model is asked to report: new or removed
# instructions that change classification behavior, content newly rendered into
# the prompt (persona exemplars, for one), a different tool name, a change in
# extraction policy.
#
# Do not bump for comments, formatting, or a reword that leaves the ask
# identical — the pin exists so that churn does not cost a model call.
EXTRACTOR_CONTRACT_VERSION = 1
```

Add the provenance record beside `ExtractionResult`:

```python
ExtractionSource = Literal["pin", "response_cache", "fresh"]


@dataclass(frozen=True)
class ExtractionProvenance:
    """How this turn's extraction was produced, recorded on the turn row."""

    source: ExtractionSource
    key: str
    contract_version: int
    model_id: str
```

`ExtractionResult` gains `provenance: ExtractionProvenance`.

`run_extraction` passes `extractor_contract_version=EXTRACTOR_CONTRACT_VERSION` and `model_id=settings.bedrock_model_id` to `extraction_key`, passes `contract_version` through to `resolved_pin.put`, and sets `source`:

- pin hit (`extraction.py:278`) → `"pin"`.
- otherwise, from the client outcome (§3.3) → `"response_cache"` on a cache hit, `"fresh"` on a real model call.

The re-read of the canonical row after `put` (`extraction.py:309`) does not change `source`. That read exists to adopt a concurrent writer's row, not to report a replay; the turn either called the model or replayed a cached response, and that is what gets recorded.

### 3.3 `server/app/bedrock/client.py`

`extract` returns only the validated object, so a response-cache hit (`client.py:127`) is invisible to callers. Move the body to a new method and keep `extract` as a wrapper:

```python
@dataclass(frozen=True)
class ExtractOutcome(Generic[ModelT]):
    content: ModelT
    cache_hit: bool
```

- `extract_result(...) -> ExtractOutcome[ModelT]` — the existing body, returning `ExtractOutcome(content=..., cache_hit=True)` on the replay branch and `cache_hit=False` after a transport call.
- `extract(...) -> ModelT` — `return self.extract_result(...).content`. Unchanged signature, so `run_reaction` (`server/app/pipeline/reaction.py:206`) and the client's own tests are untouched.

`run_extraction` calls `extract_result`.

### 3.4 `server/app/db/models.py`

- `ExtractionPinRow` gains `extractor_contract_version: Mapped[int] = mapped_column(Integer)`, with the class docstring updated: the model id is now part of the key, so a model change self-invalidates and the column is provenance plus a delete handle.
- `Turn` gains `extraction_provenance: Mapped[dict[str, Any] | None] = mapped_column(JSON_, nullable=True)`, nullable because rows written before migration 0008 have no value — the same pattern `prompt` already uses (`models.py:113`).

### 3.5 `server/app/db/repo.py`

`append_turn` gains `extraction_provenance: dict[str, Any] | None = None` and writes it to the column. Default `None` so existing test call sites that construct turns directly keep working.

### 3.6 `server/app/pipeline/orchestrator.py`

`run_turn` forwards `extraction_provenance=asdict(extraction_result.provenance)` into `repo.append_turn` (`orchestrator.py:354`). The existing extraction timing log (`orchestrator.py:300`) gains the source, so the same fact is visible live and after the fact.

### 3.7 `server/alembic/versions/0008_extractor_contract_version.py`

Revises `0007_extraction_pin`.

```python
def upgrade() -> None:
    # Existing rows are unreachable under the new key: their inputs are not
    # stored, so their hashes cannot be recomputed. Clear them rather than leave
    # rows nothing can ever read. The table is a replay cache, not a system of
    # record — the cost is re-extraction, not lost data.
    op.execute(sa.text("DELETE FROM extraction_pin"))
    op.add_column(
        "extraction_pin",
        sa.Column("extractor_contract_version", sa.Integer(), nullable=False),
    )
    op.add_column(
        "turns",
        sa.Column(
            "extraction_provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("turns", "extraction_provenance")
    op.drop_column("extraction_pin", "extractor_contract_version")
```

The `DELETE` is irreversible and the docstring says so. The delete precedes the `add_column`, which is what lets the new column be `NOT NULL` with no server default.

### 3.8 Test doubles

Eight structural doubles implement `extract` (`tests/test_api.py:52`, `:99`, `:177`; `tests/test_extraction.py:37`, `:519`, `:540`; `tests/test_orchestrator.py:67`; `tests/test_reaction.py:41`). Those on the `run_extraction` path need `extract_result`.

Add one helper in a new `server/tests/conftest.py` (the suite has none today) and mix it into the doubles that feed `run_extraction`:

```python
class ExtractResultFromExtract:
    """Gives a double `extract_result` for free: whatever its own `extract`
    returns, never a cache hit. A double has no response cache to hit."""

    def extract_result(self, content, **kwargs):
        return ExtractOutcome(content=self.extract(content, **kwargs), cache_hit=False)
```

Doubles keep their `extract` unchanged. `tests/test_reaction.py` needs nothing — reactions still call `extract`.

Tests that call `extraction_key` directly (`tests/test_extraction_pin.py:19`, `tests/test_tier0_flags.py`, `tests/golden/test_golden.py`) pass the two new arguments; the `_key` helper in `test_extraction_pin.py` gains both as defaults so existing cases read unchanged.

## 4. Provenance shape

Stored on `turns.extraction_provenance`:

```json
{
  "source": "pin",
  "key": "9f2c…",
  "contract_version": 1,
  "model_id": "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
}
```

`source` is one of `pin`, `response_cache`, `fresh`. The key is the full sha256 hex, so a row can be matched against `extraction_pin.input_hash` directly.

## 5. Testing

Every item on the issue's proof list, plus the regressions the key change touches.

**Key identity** (`tests/test_extraction_pin.py`)
- Bumping `extractor_contract_version` changes the key.
- Changing `model_id` changes the key.
- The existing cases still hold: same input same key, whitespace and case variants share a key, and answer, persona, concern, ledger, prior answers, and content fingerprint each change it.

**The exemplar trap** (`tests/test_extraction_pin.py`)
- Given a persona whose exemplars differ, the fingerprint and therefore the key differ — locking in that exemplars participate today.
- Two keys built from identical inputs and different contract versions differ, which is the mechanism a prompt fix uses to reach already-pinned inputs. Named for the trap so the next person to wire exemplars finds it.

**Pin behavior** (`tests/test_extraction_pin.py`)
- `put` persists `extractor_contract_version`; the round-trip and first-write-wins cases carry the new argument.
- A stored row under one contract version is not returned for the same inputs under another (miss, not a stale hit).

**Provenance** (`tests/test_extraction.py`, `tests/test_api.py`)
- A first extraction records `source: "fresh"` with the current key, version, and model id.
- A repeat of the same input against a live pin records `source: "pin"`.
- An input that misses the pin but hits the response cache records `source: "response_cache"` — driven by a double whose `extract_result` reports `cache_hit=True`.
- Through the API, a turn row carries a non-null `extraction_provenance` whose `key` matches a row in `extraction_pin`.

**Model policy** (`tests/test_extraction.py`)
- With a pin holding a row for an input, changing `settings.bedrock_model_id` makes the next identical turn call the model rather than replay, and the old row is left in place. This is the documented invalidation policy, and this test is the documentation that runs.

**Constant tripwire** (`tests/test_extraction.py`)
- `assert EXTRACTOR_CONTRACT_VERSION == 1`, with a comment stating that updating this test is the point: a bump should be a reviewed line in a diff, never a side effect.

**Migration**
The suite has no alembic harness — every test builds the schema with `Base.metadata.create_all` (`tests/test_extraction_pin.py:99`), and migrations 0001-0007 have no tests. 0008 follows that precedent rather than introducing a Postgres-backed harness for one revision, and `postgresql.JSONB` could not run on the in-memory SQLite the suite uses anyway. Coverage is instead:

- A model-level test that `ExtractionPinRow.extractor_contract_version` and `Turn.extraction_provenance` exist with the expected nullability, so the ORM and the migration cannot silently disagree about shape.
- Manual verification before merge: `alembic upgrade head` then `alembic downgrade -1` against a Postgres instance holding at least one `extraction_pin` row and one `turns` row, recorded in the PR description.

## 6. Out of scope

- **Wiring persona exemplars into the extraction prompt.** Tracked separately in `docs/issues/persona-exemplars-never-reach-the-model.md`, which is still an open policy question — render them or drop the field and the golden-test guidance that prescribes them. This spec makes either outcome reach pinned inputs: if exemplars get rendered, that fix is a prompt edit plus `EXTRACTOR_CONTRACT_VERSION = 2`.
- **Any model upgrade.** `settings.bedrock_model_id` is unchanged. This spec makes the upgrade safe, and hashing the model id means the upgrade itself is a one-line config change with no cleanup step.
- **Surfacing provenance in the report, the API, or the UI.** The column is written and read by nothing.
- **Pin eviction or retention.** Stranded rows after a model change are inert. If they ever need reclaiming, `model_id` and `extractor_contract_version` are both on the row and a targeted `DELETE` is enough.

## 7. Cost and risk

The key change invalidates every pin in every environment on deploy, once. Each previously answered input re-extracts on its next appearance, and because the response cache also keys on the model id, a later model change means real Bedrock calls rather than replays. That is the intended trade: extraction cost in exchange for never scoring an answer with a contract nobody is running anymore.

The narrow risk is the constant itself — a prompt-semantics change shipped without a bump replays pre-fix extractions exactly as today. The tripwire test makes the constant visible in any diff that changes it, and the bump rule sits in the constant's own docstring, next to the prompt builders someone editing it is already reading. Nothing enforces the judgment call, and that is accepted rather than overlooked: the alternative, deriving the version from source bytes, unpins the world on a typo fix.

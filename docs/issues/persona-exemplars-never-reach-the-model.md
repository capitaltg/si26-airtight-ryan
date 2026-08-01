# Persona exemplars never reach the model

### Summary

Hand-graded persona exemplars are parsed and retained in content, but no extraction prompt includes them. The project documents a worked exemplar in the persona file as the remedy for an unstable golden case, so that remedy cannot affect model output today.

### Impact

When a golden case scores unstably, the documented response is ineffective. The exemplars remain authored content that the model never sees, leaving no implementation path from the prescribed remedy to the extraction decision it is meant to stabilize.

### Suggested approach

- `_parse_exemplars` in [server/app/content/loader.py:79](../../server/app/content/loader.py#L79) parses hand-graded exemplars from each persona file and stores them in `PersonaDefinition.exemplars` at [server/app/schemas/content.py:44](../../server/app/schemas/content.py#L44).
- `_render_persona` at [server/app/pipeline/extraction.py:46](../../server/app/pipeline/extraction.py#L46) does not render `exemplars`, and neither does `build_extraction_static_prefix` at [extraction.py:104](../../server/app/pipeline/extraction.py#L104).
- [server/tests/golden/test_golden.py:8](../../server/tests/golden/test_golden.py#L8) names a worked exemplar in the persona file as the prescribed fix for an unstable case.
- Decide whether exemplars should be rendered into the extraction prompt or whether the golden-test guidance and unused content field should be removed or replaced.

### Acceptance criteria

- [ ] A chosen exemplar policy is documented.
- [ ] If exemplars remain the remedy for unstable golden cases, each relevant exemplar reaches the extraction model in a stable, test-covered prompt section.
- [ ] If exemplars do not belong in prompts, the golden-test guidance no longer directs maintainers to add them as a fix.

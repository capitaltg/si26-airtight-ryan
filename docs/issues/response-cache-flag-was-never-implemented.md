# Response-cache flag was never implemented

### Summary

The response-cache design records a confirmed decision to gate caching with `RESPONSE_CACHE_ENABLED`, defaulting on. The application has no matching setting and constructs the database-backed response cache unconditionally.

### Impact

Operators cannot disable response-cache replay through the documented environment flag. The plan and the running configuration disagree, which makes expected live-model behavior unclear for deployments and golden tests.

### Suggested approach

- The original, untracked design note recorded this decision: gate caching with `RESPONSE_CACHE_ENABLED`, default it on, and leave the live golden suite uncached. This issue preserves that decision in version control because the source note was never versioned.
- [server/app/config.py](../../server/app/config.py) has no `response_cache_enabled` setting.
- `get_bedrock_client` at [server/app/api/deps.py:44](../../server/app/api/deps.py#L44) wires `DbResponseCache(SessionLocal)` unconditionally.
- Either implement the documented flag or amend the plan to describe the unconditional cache behavior. The two currently disagree.

### Acceptance criteria

- [ ] The plan and application behavior state the same response-cache policy.
- [ ] If the flag is implemented, `RESPONSE_CACHE_ENABLED` defaults on and disabling it prevents response-cache replay.
- [ ] If the cache is intentionally unconditional, the plan no longer promises an environment gate.

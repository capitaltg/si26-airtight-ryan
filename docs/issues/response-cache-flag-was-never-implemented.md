# Response cache is unconditionally constructed

### Summary

The application constructs the database-backed response cache unconditionally. `server/app/config.py` exposes no response-cache setting.

### Impact

Operators cannot select a response-cache policy through configuration. Cache behavior is fixed in the dependency wiring.

### Suggested approach

- [server/app/config.py](../../server/app/config.py) has no `response_cache_enabled` setting.
- `get_bedrock_client` at [server/app/api/deps.py:44](../../server/app/api/deps.py#L44) wires `DbResponseCache(SessionLocal)` unconditionally.
- If deployments need a choice between cached and uncached model responses, define a configuration-backed policy and test both branches.

### Acceptance criteria

- [ ] A response-cache policy is documented in a tracked source.
- [ ] If cache configuration is added, tests cover each configured behavior.
- [ ] If cache behavior remains fixed, the dependency wiring continues to construct the intended cache explicitly.

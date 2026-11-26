# External Subagents (Profile: Claude Team Premium Primary)

On this machine, **Claude Code (`ext-claude`)** is the primary external subagent worker (Claude Team Premium with generous quota). DeepSeek Harness (`ext-dsh`) is **not** used in this profile.

## Primary Routing Policy (`ext-claude` First)
- **`ext-claude` — `sonnet` (`medium` effort) [Default Primary Worker, ~70-80%]**:
  - Use for general feature implementation, multi-file refactoring, writing/fixing tests, documentation, and first-pass code review.
  - Configured as the default model/effort in `ext-claude` (`CLAUDE_WORKER_MODEL=sonnet`, `CLAUDE_WORKER_EFFORT=medium`).
- **`ext-claude` — `opus` (`high` effort) [Senior Architect & Hard Problems, ~20-30%]**:
  - Use for complex architecture design, multi-module root-cause debugging, subtle concurrency/state bugs, and precision security/correctness reviews.
- **`ext-codex` (if enabled in `mcp_config.json`)**:
  - Optional secondary/specialist worker: reserve for sandboxed autonomous test loops (`gpt-6.2-sol`) or asset generation (`gpt-6-luna`), or when `ext-claude` hits a rate limit.
- **Main agent (Antigravity)**: Handle quick file reads, small localized edits, and direct shell checks yourself rather than spawning a subagent.

## Quota / Rate-Limit Fallback
- If `sonnet` (`medium`) struggles or fails on a complex task, escalate that task to `opus` (`high`).
- If `opus` quota is tight, keep `opus` for architecture/RCA and route implementation back to `sonnet` (`medium`/`high`).
- If `ext-claude` is rate-limited: fall back to `ext-codex` (if enabled) or execute the remaining work directly in Antigravity.

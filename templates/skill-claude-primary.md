---
name: external-subagents
description: How to delegate tasks to the locally installed Claude Code (primary: sonnet medium / opus high) and optional OpenAI Codex subagents via ext-claude and ext-codex MCP servers.
---

# External Subagents (Claude Team Premium Primary Profile)

On this machine, **Claude Code (`ext-claude`)** is the primary subagent worker (high quota via Claude Team Premium). `ext-dsh` is disabled in this profile.

## 1. `ext-claude` (Primary Worker)
- Tools: `claude_start`, `claude_send`, `claude_poll`, `claude_result`, `claude_cancel`, `claude_list`, `claude_info`
- **Default Tier (`sonnet` + `medium`)**:
  - Used automatically when `model`/`effort` are omitted (configured via `CLAUDE_WORKER_MODEL` / `CLAUDE_WORKER_EFFORT`).
  - Best for general feature implementation, refactoring, unit tests, documentation, and first-pass code reviews.
- **High-Reasoning Tier (`opus` + `high`)**:
  - Pass `model="opus", effort="high"` explicitly for architecture design, multi-module root-cause debugging, tricky concurrency/performance issues, and precision reviews.
- Flow: `claude_start(workspacePath, task, model=..., effort=..., wait=true/false)` -> `claude_send(sessionId, task)` to continue context.

## 2. `ext-codex` (Optional Specialist, if enabled)
- Tools: `codex_start`, `codex_send`, `codex_poll`, `codex_result`, `codex_cancel`, `codex_list`, `codex_info`
- Reserve for sandboxed autonomous test loops (`gpt-6.2-sol`), asset generation (`gpt-6-luna`), or fallback if `ext-claude` is rate-limited.

## Fallback & Effort Escalation
1. Start normal tasks on `sonnet` (`medium`); escalate to `opus` (`high`) if a task requires deep architectural reasoning or fails on `sonnet`.
2. If `ext-claude` hits a rate limit, fall back to `ext-codex` (if enabled) or handle the remaining work directly in Antigravity.

---
name: external-subagents
description: How to delegate tasks to the locally installed Claude Code, OpenAI Codex (GPT), and DeepSeek Harness Desktop subagents via the ext-claude, ext-codex, and ext-dsh MCP servers, including 10:2:1 quota routing and fallback rules.
---

# External Subagents (DSH Primary Profile)

Three local AI coding agents are wired as MCP subagent bridges:

1. **`ext-dsh`** (DeepSeek Harness Desktop — **10x quota, primary ~75–80%**)
   - Auto-launches `DeepSeek Harness.exe` if not already running (`127.0.0.1:5642/mcp`).
   - **Allowed models ONLY**:
     - `opencode-go` / `muse-spark-1.3-contributor` (`minimal`..`xhigh`): Fast primary worker for feature implementation, refactoring, tests, docs, 1st-pass review. **No confidential data/secrets** (contributor endpoint).
     - `opencode-go` / `deepseek-v4.1-flash` (`low`/`high`/`max`): Hard core algorithms, critical verification, large outputs (up to 384K), and confidential tasks.
   - Flow: `session_create(workspacePath, provider="opencode-go", model=...)` -> `session_send(sessionId, prompt, wait="turn")` -> `session_result(sessionId)`.

2. **`ext-claude`** (Claude Code CLI — **2x quota, ~15%**)
   - Tools: `claude_start`, `claude_send`, `claude_poll`, `claude_result`, `claude_cancel`, `claude_list`, `claude_info`
   - All models (`opus`, `sonnet`, `fable`, `haiku`, full IDs) and efforts (`low`, `medium`, `high`, `xhigh`, `max`) allowed.
   - Use `opus` (`medium`~`high`) for architecture, multi-module RCA, and precision review; `sonnet`/`haiku` for lightweight fallback.
   - Flow: `claude_start(workspacePath, task, wait=true/false)` -> `claude_send(sessionId, task)` to continue context.

3. **`ext-codex`** (OpenAI Codex / GPT Desktop CLI — **1x quota, ~5–10%**)
   - Tools: `codex_start`, `codex_send`, `codex_poll`, `codex_result`, `codex_cancel`, `codex_list`, `codex_info`
   - All models (`gpt-6.2-sol`, `gpt-6.2-astra`, `gpt-6.1-terra`, `gpt-6-luna`, etc.) and efforts (`minimal`..`ultra`) allowed.
   - Reserve for hardest unsolved problems, sandboxed autonomous test loops (`gpt-6.2-sol`), or asset generation (`gpt-6-luna`).
   - Flow: `codex_start(workspacePath, task, model=..., reasoningEffort=..., wait=true/false)` -> `codex_send(threadId, task)`.

## Quota Exhaustion Fallback Order
1. **`ext-dsh` single model limited**: Switch to the other allowed `ext-dsh` model (`deepseek-v4.1-flash` <-> `muse-spark-1.3-contributor`).
2. **`ext-dsh` fully exhausted**: Handle simple work directly in Antigravity; route implementation/review to `ext-claude` (`haiku`/`sonnet` first); escalate only critical blockers to `ext-codex`.
3. **`ext-claude` exhausted**: Route to `ext-dsh` (`deepseek-v4.1-flash` for architecture/review/RCA, `muse-spark-1.3-contributor` for implementation) with a concise handoff summary; use `ext-codex` only for unsolved blockers.
4. **`ext-codex` exhausted**: Use built-in `image-generator` for assets, `ext-claude` (`opus`) or `ext-dsh` (`deepseek-v4.1-flash`) for hard reasoning, and `ext-claude` or direct `run_command` for test loops.
5. **Escalate effort gradually**: Start at `medium` (or `low` for trivial tasks) and raise to `high`/`xhigh`/`max` only on failure.

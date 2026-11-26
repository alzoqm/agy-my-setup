# External Subagents (Profile: DSH Primary)

You have three local external subagent MCP servers available when enabled:
- `ext-claude`: Claude Code subagent (`claude_start`, `claude_send`, `claude_poll`, `claude_result`) — all models and efforts allowed
- `ext-codex`: OpenAI Codex / GPT subagent (`codex_start`, `codex_send`, `codex_poll`, `codex_result`) — all models and efforts allowed
- `ext-dsh`: DeepSeek Harness Desktop subagent (`session_create`, `session_send`, `session_poll`, `session_result`, `model_list`)

## DeepSeek Harness (`ext-dsh`) Model Restriction
For `ext-dsh` (DeepSeek Harness), ONLY use these two OpenCode models:
1. `opencode-go` / `deepseek-v4.1-flash`
2. `opencode-go` / `muse-spark-1.3-contributor`

## Quota Ratio & Task Allocation Policy
Respect the available quota ratio **OpenCode Go (`ext-dsh`) 10x : Claude (`ext-claude`) 2x : GPT (`ext-codex`) 1x**:
- **`ext-dsh` (10x, ~75-80% of work)**: Default primary worker. Use `muse-spark-1.3-contributor` (`medium`/`high`) for general implementation, refactoring, tests, docs, and first-pass review (no confidential/secret data). Use `deepseek-v4.1-flash` (`high`/`max`) for hard algorithms, critical verification, large single outputs, and confidential tasks.
- **`ext-claude` (2x, ~15% of work)**: Reserve for architecture design, multi-module root-cause debugging, and precision code review (`opus`), or fallback when `ext-dsh` is limited/unsuitable (`sonnet`/`haiku`).
- **`ext-codex` (1x, ~5-10% of work)**: Most scarce quota. Reserve for hardest unsolved reasoning/concurrency/build problems, sandboxed autonomous test loops (`gpt-6.2-sol`), or asset generation (`gpt-6-luna`).
- **Main agent (Antigravity)**: Handle simple reads, small edits, and direct commands yourself rather than spending external subagent quota.

## Quota Exhaustion / Rate-Limit Fallback
- **`ext-dsh` model/pool exhausted**: Switch between `muse-spark-1.3-contributor` and `deepseek-v4.1-flash` first; if all `ext-dsh` is exhausted, fall back to `ext-claude` (`haiku`/`sonnet` first to protect `opus`) and handle simple work directly.
- **`ext-claude` exhausted**: Route to `ext-dsh` (`deepseek-v4.1-flash` for architecture/review/bugs, `muse-spark-1.3-contributor` for implementation), transferring a brief summary of progress if resuming. Escalate only remaining blockers to `ext-codex`.
- **`ext-codex` exhausted**: Route assets to built-in `image-generator`, hard reasoning to `ext-claude` (`opus` `xhigh`/`max`) or `ext-dsh` (`deepseek-v4.1-flash` `max`), and shell/test loops to `ext-claude` or direct `run_command`.
- **Multi-agent exhaustion**: Do work directly in Antigravity, lower `effort` (`medium`/`low`), and pass minimal file/line context only.

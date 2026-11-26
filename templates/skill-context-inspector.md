---
name: context-inspector
description: Inspect real-time Antigravity conversation context window usage, token breakdown, and heaviest steps in the Context Inspector UI.
---

# Context Inspector

When the user asks to see their conversation's context usage, token breakdown, or heaviest steps:

1. Call `inspect_context` on `agy-my-setup_context-inspector` (passing `conversation_id` if inspecting the current session).
2. Summarize the key numbers returned (`used_percentage`, `used_tokens`, `cache_read_tokens`, and top heavy categories/steps) concisely.

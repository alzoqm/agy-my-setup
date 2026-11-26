#!/usr/bin/env python3
"""Cross-platform (Windows / macOS / Linux) custom configurator for agy-my-setup."""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def split_pair(spec: str, default_model: str, default_effort: str) -> dict:
    if not spec or not spec.strip():
        return {"model": default_model, "effort": default_effort}
    parts = spec.split(":", 1)
    model = parts[0].strip() or default_model
    effort = parts[1].strip() if len(parts) > 1 and parts[1].strip() else default_effort
    return {"model": model, "effort": effort}


def parse_bool_str(val: str) -> bool:
    v = val.strip().lower()
    if v in ("true", "1", "yes", "y", "on"):
        return True
    if v in ("false", "0", "no", "n", "off"):
        return False
    raise ValueError(f"Invalid boolean value: {val!r} (use true/false)")


def read_default(prompt: str, default: str) -> str:
    ans = input(f"{prompt} [{default}]: ").strip()
    return ans if ans else default


def read_bool(prompt: str, default: bool) -> bool:
    hint = "Y/n" if default else "y/N"
    ans = input(f"{prompt} [{hint}]: ").strip()
    if not ans:
        return default
    return ans.lower().startswith("y")


def detect_python_cmd() -> str:
    if sys.platform == "win32":
        return "python" if shutil.which("python") else (shutil.which("py") or sys.executable)
    return "python3" if shutil.which("python3") else (shutil.which("python") or sys.executable)


def parse_weights(spec: str, weights: dict) -> None:
    for pair in spec.split(","):
        if "=" not in pair:
            continue
        k, v_str = pair.split("=", 1)
        k = k.strip().lower()
        if k in weights:
            try:
                v = int(v_str.strip())
                if v >= 0:
                    weights[k] = v
            except ValueError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure agy-my-setup for this machine.")
    parser.add_argument("-ConfigFile", "--config-file", dest="config_file", default="")
    parser.add_argument("-Editorial", "--editorial", dest="editorial", default="")
    parser.add_argument("-ContextInspector", "--context-inspector", dest="context_inspector", default="")
    parser.add_argument("-Harnesses", "--harnesses", dest="harnesses", nargs="*", default=[])
    parser.add_argument("-Primary", "--primary", dest="primary", default="")
    parser.add_argument("-Weights", "--weights", dest="weights", default="")
    parser.add_argument("-ClaudeNormal", "--claude-normal", dest="claude_normal", default="")
    parser.add_argument("-ClaudeHard", "--claude-hard", dest="claude_hard", default="")
    parser.add_argument("-CodexNormal", "--codex-normal", dest="codex_normal", default="")
    parser.add_argument("-CodexHard", "--codex-hard", dest="codex_hard", default="")
    parser.add_argument("-CodexAsset", "--codex-asset", dest="codex_asset", default="")
    parser.add_argument("-DshNormal", "--dsh-normal", dest="dsh_normal", default="")
    parser.add_argument("-DshHard", "--dsh-hard", dest="dsh_hard", default="")
    parser.add_argument("-Interactive", "--interactive", dest="interactive", action="store_true")
    parser.add_argument("-TargetDir", "--target-dir", dest="target_dir", default=str(SCRIPT_DIR))
    args = parser.parse_args()

    target_dir = Path(args.target_dir).resolve()

    cfg = {
        "editorial": True,
        "context_inspector": True,
        "harnesses": {"dsh": True, "claude": True, "codex": True},
        "primary": "dsh",
        "weights": {"dsh": 10, "claude": 2, "codex": 1},
        "models": {
            "dsh": {"normal": "muse-spark-1.3-contributor:medium", "hard": "deepseek-v4.1-flash:high"},
            "claude": {"normal": "sonnet:medium", "hard": "opus:high"},
            "codex": {"normal": "gpt-6.2-sol:medium", "hard": "gpt-6.2-sol:high", "asset": "gpt-6-luna:medium"},
        },
    }

    setup_path = Path(args.config_file) if args.config_file else (target_dir / "setup.json")
    if setup_path.exists():
        loaded = json.loads(setup_path.read_text(encoding="utf-8"))
        if "editorial" in loaded:
            cfg["editorial"] = bool(loaded["editorial"])
        if "context_inspector" in loaded:
            cfg["context_inspector"] = bool(loaded["context_inspector"])
        if isinstance(loaded.get("harnesses"), dict):
            for k in ("dsh", "claude", "codex"):
                if k in loaded["harnesses"]:
                    cfg["harnesses"][k] = bool(loaded["harnesses"][k])
        if loaded.get("primary"):
            cfg["primary"] = str(loaded["primary"])
        if isinstance(loaded.get("weights"), dict):
            for k in ("dsh", "claude", "codex"):
                if k in loaded["weights"]:
                    cfg["weights"][k] = int(loaded["weights"][k])
        if isinstance(loaded.get("models"), dict):
            for h in ("dsh", "claude", "codex"):
                hm = loaded["models"].get(h)
                if isinstance(hm, dict):
                    for tier in ("normal", "hard", "asset"):
                        if tier in cfg["models"][h] and hm.get(tier):
                            cfg["models"][h][tier] = str(hm[tier])

    has_cli_overrides = any([
        args.editorial != "",
        args.context_inspector != "",
        len(args.harnesses) > 0,
        args.primary != "",
        args.weights != "",
        args.claude_normal != "",
        args.claude_hard != "",
        args.codex_normal != "",
        args.codex_hard != "",
        args.codex_asset != "",
        args.dsh_normal != "",
        args.dsh_hard != "",
    ])

    if args.interactive or (not has_cli_overrides and not args.config_file):
        print("\n=== agy-my-setup Custom Configurator ===")
        print("Press Enter to keep the [current/default] value.\n")

        cfg["editorial"] = read_bool("1) Enable Global Editorial Style & editorial-media MCP?", cfg["editorial"])
        cfg["context_inspector"] = read_bool("1b) Enable Context Inspector UI (context-inspector MCP)?", cfg["context_inspector"])
        cfg["harnesses"]["dsh"] = read_bool("2) Enable ext-dsh (DeepSeek Harness Desktop)?", cfg["harnesses"]["dsh"])
        cfg["harnesses"]["claude"] = read_bool("3) Enable ext-claude (Claude Code CLI)?", cfg["harnesses"]["claude"])
        cfg["harnesses"]["codex"] = read_bool("4) Enable ext-codex (OpenAI Codex / GPT)?", cfg["harnesses"]["codex"])

        enabled_list = [h for h in ("dsh", "claude", "codex") if cfg["harnesses"][h]]
        if enabled_list:
            default_prim = cfg["primary"] if cfg["primary"] in enabled_list else enabled_list[0]
            p_in = read_default(f"5) Primary harness ({' / '.join(enabled_list)})", default_prim).lower()
            cfg["primary"] = p_in if p_in in enabled_list else default_prim

            if len(enabled_list) > 1:
                w_def = ",".join(f"{h}={cfg['weights'][h]}" for h in enabled_list)
                w_in = read_default("6) Quota weights (e.g. claude=8,codex=2)", w_def)
                parse_weights(w_in, cfg["weights"])

            if cfg["harnesses"]["claude"]:
                cfg["models"]["claude"]["normal"] = read_default("   - Claude normal tier (model:effort)", cfg["models"]["claude"]["normal"])
                cfg["models"]["claude"]["hard"] = read_default("   - Claude hard/architect tier (model:effort)", cfg["models"]["claude"]["hard"])
            if cfg["harnesses"]["codex"]:
                cfg["models"]["codex"]["normal"] = read_default("   - Codex normal tier (model:effort)", cfg["models"]["codex"]["normal"])
                cfg["models"]["codex"]["hard"] = read_default("   - Codex hard tier (model:effort)", cfg["models"]["codex"]["hard"])
                cfg["models"]["codex"]["asset"] = read_default("   - Codex asset tier (model:effort)", cfg["models"]["codex"]["asset"])
            if cfg["harnesses"]["dsh"]:
                cfg["models"]["dsh"]["normal"] = read_default("   - DSH normal tier (model:effort)", cfg["models"]["dsh"]["normal"])
                cfg["models"]["dsh"]["hard"] = read_default("   - DSH hard tier (model:effort)", cfg["models"]["dsh"]["hard"])
        else:
            cfg["primary"] = "none"

    if args.editorial != "":
        cfg["editorial"] = parse_bool_str(args.editorial)
    if args.context_inspector != "":
        cfg["context_inspector"] = parse_bool_str(args.context_inspector)

    if args.harnesses:
        flat = [x.strip().lower() for item in args.harnesses for x in item.split(",") if x.strip()]
        for k in ("dsh", "claude", "codex"):
            cfg["harnesses"][k] = k in flat

    enabled = [h for h in ("dsh", "claude", "codex") if cfg["harnesses"][h]]

    if args.primary:
        p = args.primary.strip().lower()
        if p == "none" or p in enabled:
            cfg["primary"] = p
        else:
            raise ValueError(f"Invalid --primary '{args.primary}'. Enabled harnesses: {', '.join(enabled)}")
    elif not enabled:
        cfg["primary"] = "none"
    elif cfg["primary"] not in enabled:
        cfg["primary"] = enabled[0]

    if args.weights:
        parse_weights(args.weights, cfg["weights"])

    if args.claude_normal:
        cfg["models"]["claude"]["normal"] = args.claude_normal
    if args.claude_hard:
        cfg["models"]["claude"]["hard"] = args.claude_hard
    if args.codex_normal:
        cfg["models"]["codex"]["normal"] = args.codex_normal
    if args.codex_hard:
        cfg["models"]["codex"]["hard"] = args.codex_hard
    if args.codex_asset:
        cfg["models"]["codex"]["asset"] = args.codex_asset
    if args.dsh_normal:
        cfg["models"]["dsh"]["normal"] = args.dsh_normal
    if args.dsh_hard:
        cfg["models"]["dsh"]["hard"] = args.dsh_hard

    p_claude_norm = split_pair(cfg["models"]["claude"]["normal"], "sonnet", "medium")
    p_claude_hard = split_pair(cfg["models"]["claude"]["hard"], "opus", "high")
    p_codex_norm = split_pair(cfg["models"]["codex"]["normal"], "gpt-6.2-sol", "medium")
    p_codex_hard = split_pair(cfg["models"]["codex"]["hard"], "gpt-6.2-sol", "high")
    p_codex_asset = split_pair(cfg["models"]["codex"]["asset"], "gpt-6-luna", "medium")
    p_dsh_norm = split_pair(cfg["models"]["dsh"]["normal"], "muse-spark-1.3-contributor", "medium")
    p_dsh_hard = split_pair(cfg["models"]["dsh"]["hard"], "deepseek-v4.1-flash", "high")

    py_cmd = detect_python_cmd()
    servers = {}

    if cfg["editorial"]:
        servers["editorial-media"] = {
            "command": py_cmd,
            "args": ["-X", "utf8", "${PLUGIN_ROOT}/scripts/editorial_media_server.py"],
        }

    if cfg["context_inspector"]:
        servers["context-inspector"] = {
            "command": py_cmd,
            "args": ["-X", "utf8", "${PLUGIN_ROOT}/scripts/context_server.py"],
        }

    if cfg["harnesses"]["claude"]:
        servers["ext-claude"] = {
            "command": py_cmd,
            "args": ["-X", "utf8", "${PLUGIN_ROOT}/scripts/claude_workers_server.py"],
            "env": {
                "CLAUDE_WORKER_MODEL": p_claude_norm["model"],
                "CLAUDE_WORKER_EFFORT": p_claude_norm["effort"],
            },
        }

    if cfg["harnesses"]["codex"]:
        servers["ext-codex"] = {
            "command": py_cmd,
            "args": ["-X", "utf8", "${PLUGIN_ROOT}/scripts/codex_workers_server.py"],
            "env": {
                "CODEX_WORKER_MODEL": p_codex_norm["model"],
                "CODEX_WORKER_EFFORT": p_codex_norm["effort"],
            },
        }

    if cfg["harnesses"]["dsh"]:
        servers["ext-dsh"] = {
            "command": py_cmd,
            "args": ["-X", "utf8", "${PLUGIN_ROOT}/scripts/dsh_bridge.py"],
            "env": {"DSH_MCP_TOKEN": "${DSH_MCP_TOKEN}"},
            "variables": [
                {
                    "name": "DSH_MCP_TOKEN",
                    "title": "DeepSeek Harness MCP Token",
                    "description": "DeepSeek Harness Desktop의 MCP Bearer 토큰을 입력하세요 (로컬 서버 127.0.0.1:5642/mcp 인증용).",
                }
            ],
        }

    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "mcp_config.json").write_text(
        json.dumps({"mcpServers": servers}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    subagent_rule = ""
    subagent_skill = ""

    if enabled:
        total_weight = sum(max(0, int(cfg["weights"][h])) for h in enabled) or len(enabled)
        ordered = ([cfg["primary"]] if cfg["primary"] in enabled else []) + [h for h in enabled if h != cfg["primary"]]

        server_lines = []
        alloc_lines = []
        skill_sections = []

        for h in ordered:
            w = int(cfg["weights"][h])
            pct = round((w / total_weight) * 100)
            role_tag = f"**Primary Worker (~{pct}%)**" if h == cfg["primary"] else f"Secondary/Specialist (~{pct}%)"

            if h == "dsh":
                server_lines.append("- `ext-dsh`: DeepSeek Harness Desktop (`session_create`, `session_send`, `session_poll`, `session_result`, `model_list`)")
                alloc_lines.append(f"- **`ext-dsh` [{role_tag}, weight={w}]**:")
                alloc_lines.append(f"  - Normal tasks (implementation, refactoring, tests, docs, 1st-pass review — no secrets): `opencode-go/{p_dsh_norm['model']}` (effort `{p_dsh_norm['effort']}`).")
                alloc_lines.append(f"  - Hard/confidential tasks (algorithms, critical verification, large outputs): `opencode-go/{p_dsh_hard['model']}` (effort `{p_dsh_hard['effort']}`).")
                skill_sections.append(
                    f"### `ext-dsh` ({role_tag})\n"
                    f"- Allowed models ONLY: `opencode-go/{p_dsh_norm['model']}` (normal, no secrets) and `opencode-go/{p_dsh_hard['model']}` (hard/confidential).\n"
                    f"- Default tiers: normal=`{p_dsh_norm['model']}` (`{p_dsh_norm['effort']}`), hard=`{p_dsh_hard['model']}` (`{p_dsh_hard['effort']}`).\n"
                    "- Flow: `session_create(workspacePath, provider=\"opencode-go\", model=...)` -> `session_send(sessionId, prompt, wait=\"turn\")` -> `session_result(sessionId)`.\n"
                )
            elif h == "claude":
                server_lines.append(f"- `ext-claude`: Claude Code CLI (`claude_start`, `claude_send`, `claude_poll`, `claude_result`, `claude_info`) — default `{p_claude_norm['model']}` (`{p_claude_norm['effort']}`)")
                alloc_lines.append(f"- **`ext-claude` [{role_tag}, weight={w}]**:")
                alloc_lines.append(f"  - Normal/default tier: `{p_claude_norm['model']}` (effort `{p_claude_norm['effort']}`) for feature implementation, refactoring, tests, docs, and 1st-pass review.")
                alloc_lines.append(f"  - Hard/architect tier: `{p_claude_hard['model']}` (effort `{p_claude_hard['effort']}`) for architecture design, multi-module root-cause debugging, and precision reviews.")
                skill_sections.append(
                    f"### `ext-claude` ({role_tag})\n"
                    "- Tools: `claude_start`, `claude_send`, `claude_poll`, `claude_result`, `claude_cancel`, `claude_list`, `claude_info`.\n"
                    f"- Default tier (used when `model`/`effort` omitted): `{p_claude_norm['model']}` (`{p_claude_norm['effort']}`).\n"
                    f"- Hard/architect tier (pass explicitly): `model=\"{p_claude_hard['model']}\", effort=\"{p_claude_hard['effort']}\"`.\n"
                    "- Flow: `claude_start(workspacePath, task, wait=true/false)` -> `claude_send(sessionId, task)`.\n"
                )
            elif h == "codex":
                server_lines.append(f"- `ext-codex`: OpenAI Codex / GPT (`codex_start`, `codex_send`, `codex_poll`, `codex_result`, `codex_info`) — default `{p_codex_norm['model']}` (`{p_codex_norm['effort']}`)")
                alloc_lines.append(f"- **`ext-codex` [{role_tag}, weight={w}]**:")
                alloc_lines.append(f"  - Normal/default tier: `{p_codex_norm['model']}` (effort `{p_codex_norm['effort']}`).")
                alloc_lines.append(f"  - Hard/sandboxed test loops: `{p_codex_hard['model']}` (effort `{p_codex_hard['effort']}`); asset generation: `{p_codex_asset['model']}` (effort `{p_codex_asset['effort']}`).")
                skill_sections.append(
                    f"### `ext-codex` ({role_tag})\n"
                    "- Tools: `codex_start`, `codex_send`, `codex_poll`, `codex_result`, `codex_cancel`, `codex_list`, `codex_info`.\n"
                    f"- Default tier: `{p_codex_norm['model']}` (`{p_codex_norm['effort']}`); hard tier: `{p_codex_hard['model']}` (`{p_codex_hard['effort']}`); asset tier: `{p_codex_asset['model']}` (`{p_codex_asset['effort']}`).\n"
                    "- Flow: `codex_start(workspacePath, task, model=..., reasoningEffort=..., wait=true/false)` -> `codex_send(threadId, task)`.\n"
                )

        dsh_block = ""
        if cfg["harnesses"]["dsh"]:
            dsh_block = (
                "\n## DeepSeek Harness (`ext-dsh`) Model Restriction\n"
                "For `ext-dsh`, ONLY use these two OpenCode models:\n"
                "1. `opencode-go` / `deepseek-v4.1-flash`\n"
                "2. `opencode-go` / `muse-spark-1.3-contributor`\n"
            )

        fallback_chain = " -> ".join(f"`ext-{h}`" for h in ordered)

        subagent_rule = (
            f"# External Subagents (Custom Machine Config)\n\n"
            f"Enabled external subagent MCP servers on this machine (primary: `ext-{cfg['primary']}`):\n"
            + "\n".join(server_lines)
            + "\n"
            + dsh_block
            + "\n## Task Allocation & Model Tiers\n"
            + "\n".join(alloc_lines)
            + "\n- **Main agent (Antigravity)**: Handle simple file reads, small localized edits, and direct shell checks yourself rather than spawning a subagent.\n\n"
            "## Quota Exhaustion / Fallback Order\n"
            "- Escalate within the active harness first (normal tier -> hard tier).\n"
            f"- If a harness is rate-limited or unavailable, fall back along: {fallback_chain} -> Antigravity direct execution.\n"
        )

        subagent_skill = (
            "---\n"
            "name: external-subagents\n"
            f"description: Delegate tasks to the enabled external subagent MCP servers ({', '.join(ordered)}) using this machine's custom model, effort, and quota routing config.\n"
            "---\n\n"
            "# External Subagents (Active Machine Config)\n\n"
            f"Primary harness: **`ext-{cfg['primary']}`** | Fallback order: {fallback_chain}\n\n"
            + "\n".join(skill_sections)
            + "\n## Fallback & Escalation\n"
            "1. Start normal tasks on the harness's normal tier; escalate to its hard tier on complex architecture, RCA, or failure.\n"
            f"2. If the primary harness is rate-limited, fall back in order: {fallback_chain} -> direct Antigravity execution.\n"
        )

    rules_parts = []
    editorial_tpl = SCRIPT_DIR / "templates" / "rules-editorial.md"
    if cfg["editorial"] and editorial_tpl.exists():
        rules_parts.append(editorial_tpl.read_text(encoding="utf-8").strip())
    if subagent_rule:
        rules_parts.append(subagent_rule.strip())

    rules_dir = target_dir / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "AGENTS.md").write_text("\n\n---\n\n".join(rules_parts) + "\n", encoding="utf-8")

    skill_dir = target_dir / "skills" / "external-subagents"
    if subagent_skill:
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(subagent_skill.strip() + "\n", encoding="utf-8")
    elif skill_dir.exists():
        shutil.rmtree(skill_dir)

    ctx_skill_dir = target_dir / "skills" / "context-inspector"
    ctx_tpl = SCRIPT_DIR / "templates" / "skill-context-inspector.md"
    if cfg["context_inspector"] and ctx_tpl.exists():
        ctx_skill_dir.mkdir(parents=True, exist_ok=True)
        (ctx_skill_dir / "SKILL.md").write_text(ctx_tpl.read_text(encoding="utf-8"), encoding="utf-8")
    elif not cfg["context_inspector"] and ctx_skill_dir.exists():
        shutil.rmtree(ctx_skill_dir)

    (target_dir / "setup.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\nConfigured agy-my-setup at: {target_dir}")
    print(f"  Python Command  : {py_cmd}")
    print(f"  Editorial Style : {cfg['editorial']}")
    print(f"  Context Inspect : {cfg['context_inspector']}")
    print(f"  MCP Servers     : {', '.join(servers.keys())}")
    if enabled:
        print(f"  Primary Harness : ext-{cfg['primary']}")
        if cfg["harnesses"]["claude"]:
            print(f"  Claude Tiers    : normal={p_claude_norm['model']}:{p_claude_norm['effort']}, hard={p_claude_hard['model']}:{p_claude_hard['effort']}")
        if cfg["harnesses"]["codex"]:
            print(f"  Codex Tiers     : normal={p_codex_norm['model']}:{p_codex_norm['effort']}, hard={p_codex_hard['model']}:{p_codex_hard['effort']}, asset={p_codex_asset['model']}:{p_codex_asset['effort']}")
        if cfg["harnesses"]["dsh"]:
            print(f"  DSH Tiers       : normal={p_dsh_norm['model']}:{p_dsh_norm['effort']}, hard={p_dsh_hard['model']}:{p_dsh_hard['effort']}")
    print(f"  Saved Config    : {target_dir / 'setup.json'}")
    print("Restart or toggle the plugin in Antigravity Customizations to reload.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

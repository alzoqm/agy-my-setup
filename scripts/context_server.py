#!/usr/bin/env python3
"""Pure-Python MCP server + MCP App (SEP-1865) for Antigravity Context Inspector."""

import glob
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

APP_URI = "ui://context-inspector/app.html"
AGY_DIR = Path.home() / ".gemini" / "antigravity"
BRAIN_DIR = AGY_DIR / "brain"
ANNOTATIONS_DIR = AGY_DIR / "annotations"
CONFIG_DIR = Path.home() / ".gemini" / "config"
GEMINI_MD = Path.home() / ".gemini" / "GEMINI.md"
UI_HTML_PATH = Path(__file__).resolve().parent.parent / "ui" / "app.html"

DEFAULT_CONTEXT_LIMIT = 1048576  # 1M tokens


def est_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def scan_rules_tokens() -> dict:
    files = []
    total = 0
    candidates = []
    if GEMINI_MD.exists():
        candidates.append(GEMINI_MD)
    for pattern in [
        str(CONFIG_DIR / "rules" / "**" / "*.md"),
        str(CONFIG_DIR / "plugins" / "*" / "rules" / "*.md"),
    ]:
        for p in glob.glob(pattern, recursive=True):
            candidates.append(Path(p))
    seen = set()
    for p in candidates:
        rp = str(p.resolve())
        if rp in seen:
            continue
        seen.add(rp)
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
            t = est_tokens(txt)
            total += t
            files.append({"path": p.name, "full_path": rp, "tokens": t})
        except OSError:
            pass
    files.sort(key=lambda x: x["tokens"], reverse=True)
    return {"total_tokens": total, "budget": 20000, "files": files[:10]}


def fetch_conversation_titles() -> dict[str, dict]:
    """Fetch user-visible titles from local annotations/*.pbtxt and ConversationService."""
    titles = {}
    if ANNOTATIONS_DIR.exists():
        for pb in ANNOTATIONS_DIR.glob("*.pbtxt"):
            cid = pb.stem
            try:
                raw = pb.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r'title:"((?:[^"\\]|\\.)*)"', raw)
                if m:
                    t = bytes(m.group(1), "utf-8").decode("unicode_escape", errors="ignore")
                    # Fix UTF-8 bytes if unicode_escape produced latin1
                    try:
                        t = t.encode("latin1").decode("utf-8")
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        pass
                    titles[cid] = {"title": t, "run_state": ""}
            except OSError:
                pass

    ls_addr = os.environ.get("ANTIGRAVITY_LS_ADDRESS")
    csrf = os.environ.get("ANTIGRAVITY_CSRF_TOKEN")
    if not ls_addr or not csrf:
        return titles
    try:
        req = urllib.request.Request(
            f"http://{ls_addr}/product.v1.ConversationService/ListConversations",
            data=b'{"pageSize": 50, "includeArchived": false}',
            headers={
                "Content-Type": "application/json",
                "Connect-Protocol-Version": "1",
                "x-antigravity-csrf-token": csrf,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for c in data.get("conversations", []):
                cid = c.get("id")
                if not cid:
                    continue
                ann_title = (c.get("annotations") or {}).get("title") or ""
                summary = (c.get("state") or {}).get("summary") or ""
                run_state = (c.get("state") or {}).get("runState") or ""
                titles[cid] = {
                    "title": ann_title or summary,
                    "run_state": run_state,
                }
    except Exception:
        pass
    return titles


def quick_transcript_meta(tfile: Path) -> tuple[str, int, str]:
    """Return (fallback_title, latest_used_tokens, latest_model) from transcript.jsonl."""
    fallback_title = ""
    used = 0
    model = ""
    try:
        with tfile.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = obj.get("type")
                if t == "USER_INPUT" and not fallback_title:
                    txt = str(obj.get("content", "")).replace("<USER_REQUEST>", "").replace("</USER_REQUEST>", "").strip()
                    txt = " ".join(txt.split())
                    if txt:
                        fallback_title = txt[:48] + ("..." if len(txt) > 48 else "")
                elif t == "PLANNER_RESPONSE":
                    in_t = int(obj.get("input_tokens") or 0)
                    cr_t = int(obj.get("cache_read_tokens") or 0)
                    if in_t > 0 or cr_t > 0:
                        used = in_t + cr_t
                        model = obj.get("model") or model
    except OSError:
        pass
    return fallback_title, used, model


def list_recent_conversations(limit: int = 20) -> list[dict]:
    items = []
    if not BRAIN_DIR.exists():
        return items
    api_titles = fetch_conversation_titles()
    for conv_dir in BRAIN_DIR.iterdir():
        if not conv_dir.is_dir():
            continue
        tfile = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
        if tfile.exists():
            try:
                st = tfile.stat()
                cid = conv_dir.name
                items.append({
                    "id": cid,
                    "tfile": tfile,
                    "mtime": st.st_mtime,
                    "size_kb": round(st.st_size / 1024, 1),
                })
            except OSError:
                pass
    items.sort(key=lambda x: x["mtime"], reverse=True)
    result = []
    for it in items[:limit]:
        cid = it["id"]
        fb_title, used, model = quick_transcript_meta(it["tfile"])
        meta = api_titles.get(cid, {})
        title = meta.get("title") or fb_title or f"세션 {cid[:8]}"
        updated_str = datetime.fromtimestamp(it["mtime"]).strftime("%m/%d %H:%M")
        result.append({
            "id": cid,
            "title": title,
            "model": model or "unknown",
            "used_tokens": used,
            "used_percentage": round(min(100.0, (used / DEFAULT_CONTEXT_LIMIT) * 100.0), 1) if used > 0 else 0.0,
            "updated": updated_str,
            "size_kb": it["size_kb"],
            "run_state": meta.get("run_state", ""),
        })
    return result


def analyze_conversation(conversation_id: str | None = None, include_all_details: bool = True) -> dict:
    recent = list_recent_conversations(15)
    target_id = conversation_id or os.environ.get("ANTIGRAVITY_CONVERSATION_ID")
    if not target_id and recent:
        target_id = recent[0]["id"]

    if not target_id:
        return {"error": "No conversation transcript found.", "recent_conversations": recent}

    tfile = BRAIN_DIR / target_id / ".system_generated" / "logs" / "transcript.jsonl"
    if not tfile.exists():
        return {
            "error": f"Transcript not found for {target_id}",
            "conversation_id": target_id,
            "recent_conversations": recent,
        }

    user_tokens = 0
    model_tokens = 0
    tool_tokens = 0
    turns = []
    heavy_steps = []
    latest_input = 0
    latest_cache_read = 0
    latest_output = 0
    latest_model = "unknown"
    step_count = 0

    with tfile.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            step_count += 1
            stype = obj.get("type", "UNKNOWN")
            content = obj.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            thinking = obj.get("thinking", "") or ""
            ctok = est_tokens(content) + est_tokens(thinking)

            if "COMPACT" in stype or "CHECKPOINT" in stype:
                user_tokens = 0
                model_tokens = 0
                tool_tokens = 0
                heavy_steps = []
                continue

            if stype == "USER_INPUT":
                user_tokens += ctok
            elif stype == "PLANNER_RESPONSE":
                in_t = int(obj.get("input_tokens") or 0)
                cr_t = int(obj.get("cache_read_tokens") or 0)
                out_t = int(obj.get("output_tokens") or 0)
                if in_t > 0 or cr_t > 0:
                    latest_input = in_t
                    latest_cache_read = cr_t
                    latest_output = out_t
                    latest_model = obj.get("model") or latest_model
                    turns.append({
                        "step": obj.get("step_index", step_count),
                        "input_tokens": in_t + cr_t,
                        "cache_read_tokens": cr_t,
                        "output_tokens": out_t,
                    })
                model_tokens += out_t if out_t > 0 else ctok
            else:
                tool_tokens += ctok

            if ctok >= 300:
                preview = content.replace("\n", " ")[:90]
                heavy_steps.append({
                    "step": obj.get("step_index", step_count),
                    "type": stype,
                    "tokens_est": ctok,
                    "preview": preview,
                })

    heavy_steps.sort(key=lambda x: x["tokens_est"], reverse=True)
    rules_info = scan_rules_tokens()
    context_limit = DEFAULT_CONTEXT_LIMIT
    used_total = (latest_input + latest_cache_read) if (latest_input + latest_cache_read) > 0 else (user_tokens + model_tokens + tool_tokens + rules_info["total_tokens"])
    used_pct = round(min(100.0, (used_total / context_limit) * 100.0), 2)
    remaining_tokens = max(0, context_limit - used_total)

    rules_est = min(rules_info["total_tokens"], 20000, used_total)
    raw_history = user_tokens + model_tokens + tool_tokens
    # Normalize history breakdown so categories never exceed actual used_total
    avail_after_rules = max(0, used_total - rules_est)
    if raw_history > avail_after_rules and raw_history > 0:
        # Reserve ~35% (capped at 14k) for system prompt & tool schemas when compressed/large
        sys_reserve = min(14000, int(avail_after_rules * 0.35))
        hist_budget = max(0, avail_after_rules - sys_reserve)
        scale = hist_budget / raw_history
        user_est = int(user_tokens * scale)
        model_est = int(model_tokens * scale)
        tool_est = max(0, hist_budget - user_est - model_est)
        system_overhead = max(0, used_total - rules_est - user_est - model_est - tool_est)
    else:
        user_est = user_tokens
        model_est = model_tokens
        tool_est = tool_tokens
        system_overhead = max(0, avail_after_rules - raw_history)

    result = {
        "conversation_id": target_id,
        "conversation_title": next((c["title"] for c in recent if c["id"] == target_id), target_id[:8]),
        "model": latest_model,
        "context_limit": context_limit,
        "used_tokens": used_total,
        "remaining_tokens": remaining_tokens,
        "used_percentage": used_pct,
        "latest_turn": {
            "input_tokens": latest_input,
            "cache_read_tokens": latest_cache_read,
            "output_tokens": latest_output,
        },
        "breakdown": {
            "system_and_tools_est": system_overhead,
            "rules_est": rules_est,
            "rules_raw": rules_info["total_tokens"],
            "user_messages_est": user_est,
            "model_responses_est": model_est,
            "tool_outputs_est": tool_est,
        },
        "rules_files": rules_info["files"],
        "turns": turns[-24:],
        "heavy_steps": heavy_steps[:8],
        "step_count": step_count,
        "recent_conversations": recent,
    }
    if include_all_details:
        sessions_by_id = {target_id: {k: v for k, v in result.items() if k != "recent_conversations"}}
        for c in recent:
            cid = c["id"]
            if cid not in sessions_by_id:
                sub = analyze_conversation(cid, include_all_details=False)
                if "error" not in sub:
                    sessions_by_id[cid] = {k: v for k, v in sub.items() if k != "recent_conversations"}
        result["sessions_by_id"] = sessions_by_id
    return result


def load_app_html() -> str:
    if UI_HTML_PATH.exists():
        return UI_HTML_PATH.read_text(encoding="utf-8")
    return "<html><body><h3>Context Inspector UI file missing.</h3></body></html>"


def send_response(msg_id, result):
    out = {"jsonrpc": "2.0", "id": msg_id, "result": result}
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def send_error(msg_id, code, message):
    out = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle_request(req: dict):
    method = req.get("method")
    msg_id = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        send_response(msg_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": {"name": "context-inspector", "version": "1.0.0"},
        })
        return

    if method == "notifications/initialized":
        return

    if method == "ping":
        send_response(msg_id, {})
        return

    if method == "tools/list":
        send_response(msg_id, {
            "tools": [
                {
                    "name": "inspect_context",
                    "title": "Context Inspector",
                    "description": "Inspect real-time Antigravity conversation context window usage, token breakdown, and heaviest steps in the Context Inspector UI.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "conversation_id": {
                                "type": "string",
                                "description": "Optional conversation UUID. Defaults to the latest active conversation.",
                            }
                        },
                    },
                    "_meta": {
                        "ui": {"resourceUri": APP_URI},
                        "com.google.antigravity/ui": {
                            "entrypoints": [
                                {"type": "global", "title": "Context Inspector"},
                                {"type": "aux_pane", "title": "Context Inspector"}
                            ]
                        },
                    },
                },
                {
                    "name": "refresh_context",
                    "title": "Refresh Context Metrics",
                    "description": "Fetch updated context metrics for a conversation (used by the Context Inspector UI).",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "conversation_id": {"type": "string"}
                        },
                    },
                    "_meta": {
                        "ui": {"visibility": ["app", "model"]}
                    },
                },
            ]
        })
        return

    if method == "resources/list":
        send_response(msg_id, {
            "resources": [
                {
                    "uri": APP_URI,
                    "name": "Context Inspector UI",
                    "description": "Interactive Context Window & Token Breakdown Dashboard",
                    "mimeType": "text/html;profile=mcp-app",
                }
            ]
        })
        return

    if method == "resources/read":
        uri = params.get("uri")
        if uri == APP_URI:
            send_response(msg_id, {
                "contents": [
                    {
                        "uri": APP_URI,
                        "mimeType": "text/html;profile=mcp-app",
                        "text": load_app_html(),
                        "_meta": {"ui": {"prefersBorder": False}},
                    }
                ]
            })
        else:
            send_error(msg_id, -32602, f"Unknown resource URI: {uri}")
        return

    if method == "tools/call":
        tname = params.get("name")
        args = params.get("arguments") or {}
        if tname in ("inspect_context", "refresh_context"):
            data = analyze_conversation(args.get("conversation_id"))
            if "error" in data:
                summary = f"Context Inspector: {data['error']}"
            else:
                summary = (
                    f"Conversation {data['conversation_id']} ({data['model']}): "
                    f"{data['used_tokens']:,} / {data['context_limit']:,} tokens used ({data['used_percentage']}%). "
                    f"Cache read: {data['latest_turn']['cache_read_tokens']:,}, "
                    f"Tool outputs est: {data['breakdown']['tool_outputs_est']:,}, "
                    f"Rules est: {data['breakdown']['rules_est']:,}."
                )
            send_response(msg_id, {
                "content": [{"type": "text", "text": summary}],
                "structuredContent": data,
            })
            return
        send_error(msg_id, -32601, f"Unknown tool: {tname}")
        return

    if msg_id is not None:
        send_error(msg_id, -32601, f"Method not found: {method}")


def main():
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
        except json.JSONDecodeError:
            continue
        handle_request(req)


if __name__ == "__main__":
    main()

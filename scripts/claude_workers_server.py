"""claude-workers: stdio MCP server that dispatches tasks to the local Claude Code CLI.

Standard library only. Every task runs as `claude -p --output-format stream-json --verbose`
in the background; follow-ups use `--resume <sessionId>` to preserve conversation context.

Tools: claude_start, claude_send, claude_poll, claude_result, claude_cancel, claude_list, claude_info
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid

SERVER = {"name": "ext-claude", "version": "1.1.0"}
DEFAULT_MODEL = os.environ.get("CLAUDE_WORKER_MODEL") or None
DEFAULT_EFFORT = os.environ.get("CLAUDE_WORKER_EFFORT") or None
HOME = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("PLUGIN_DATA") or HOME
JOBDIR = os.path.join(DATA_DIR, "claude_jobs")
os.makedirs(JOBDIR, exist_ok=True)
JOBS = {}
LOCK = threading.Lock()
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache"}


def claude_exe():
    if os.environ.get("CLAUDE_EXE") and os.path.exists(os.environ["CLAUDE_EXE"]):
        return os.environ["CLAUDE_EXE"]
    for rel in (r"~\.local\bin\claude.exe", r"~\.local\bin\claude", "/opt/homebrew/bin/claude", "/usr/local/bin/claude"):
        cand = os.path.expanduser(rel)
        if os.path.exists(cand):
            return cand
    found = shutil.which("claude")
    if found:
        return found
    raise RuntimeError("claude CLI not found (set CLAUDE_EXE to override)")


def snapshot(root, limit=20000):
    out = {}
    if not root or not os.path.isdir(root):
        return out
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for f in fns:
            p = os.path.join(dp, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out[os.path.relpath(p, root)] = (st.st_size, st.st_mtime_ns)
            if len(out) >= limit:
                return out
    return out


def diff_snap(a, b):
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    modified = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    return {"added": added, "modified": modified, "deleted": removed}


class Job:
    def __init__(self, cwd, prompt, permission_mode, model, effort, disable_mcps, session_id=None):
        self.id = uuid.uuid4().hex[:12]
        self.cwd = cwd
        self.prompt = prompt
        self.permission_mode = permission_mode
        self.model = model
        self.effort = effort
        self.disable_mcps = disable_mcps
        self.session_id = session_id
        self.state = "starting"
        self.started = time.time()
        self.ended = None
        self.messages = []
        self.final_result = None
        self.errors = []
        self.usage = None
        self.cost_usd = None
        self.proc = None
        self.rc = None
        self.log = os.path.join(JOBDIR, self.id + ".jsonl")
        self.before = snapshot(self.cwd)
        self.changes = None

    def argv(self):
        cmd = [
            claude_exe(),
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            self.permission_mode,
        ]
        if self.model:
            cmd += ["--model", self.model]
        if self.effort:
            cmd += ["--effort", self.effort]
        if self.disable_mcps:
            cmd += ["--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
        if self.session_id:
            cmd += ["--resume", self.session_id]
        cmd += ["--", self.prompt]
        return cmd

    def status(self, detail="summary"):
        d = {
            "jobId": self.id,
            "sessionId": self.session_id,
            "state": self.state,
            "elapsedSec": round((self.ended or time.time()) - self.started, 1),
            "exitCode": self.rc,
            "costUsd": self.cost_usd,
        }
        if detail == "summary":
            d["lastMessage"] = (self.final_result or (self.messages[-1] if self.messages else ""))[:1200]
            if self.errors:
                d["errors"] = self.errors[-3:]
            if self.changes is not None:
                d["changes"] = self.changes
            return d
        d["result"] = self.final_result if self.final_result is not None else "\n\n".join(self.messages)
        d["errors"] = self.errors
        d["usage"] = self.usage
        d["changes"] = self.changes
        d["logPath"] = self.log
        return d


def run_job(j):
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        j.proc = subprocess.Popen(
            j.argv(),
            cwd=j.cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
        j.state = "running"
    except Exception as e:
        j.state = "failed"
        j.errors.append(repr(e))
        j.ended = time.time()
        return

    def read_err():
        for line in j.proc.stderr:
            s = line.strip()
            if s:
                j.errors.append(s[:500])

    et = threading.Thread(target=read_err, daemon=True)
    et.start()

    with open(j.log, "w", encoding="utf-8") as lf:
        for line in j.proc.stdout:
            lf.write(line)
            lf.flush()
            s = line.strip()
            if not s:
                continue
            try:
                ev = json.loads(s)
            except Exception:
                continue
            if ev.get("session_id") and not j.session_id:
                j.session_id = ev["session_id"]
            t = ev.get("type")
            if t == "assistant":
                msg = ev.get("message") or {}
                for blk in msg.get("content") or []:
                    if isinstance(blk, dict) and blk.get("type") == "text" and blk.get("text"):
                        j.messages.append(blk["text"])
            elif t == "result":
                if ev.get("result") is not None:
                    j.final_result = ev["result"]
                if ev.get("usage"):
                    j.usage = ev["usage"]
                if ev.get("total_cost_usd") is not None:
                    j.cost_usd = ev["total_cost_usd"]
                if ev.get("is_error") and ev.get("result"):
                    j.errors.append(str(ev["result"])[:500])

    j.rc = j.proc.wait()
    et.join(timeout=2)
    j.changes = diff_snap(j.before, snapshot(j.cwd))
    j.ended = time.time()
    if j.state != "cancelled":
        j.state = "completed" if j.rc == 0 else "failed"


def start_job(cwd, prompt, permission_mode, model, effort, disable_mcps, session_id=None):
    if not os.path.isdir(cwd):
        raise ValueError(f"workspacePath does not exist: {cwd}")
    j = Job(cwd, prompt, permission_mode, model, effort, disable_mcps, session_id=session_id)
    with LOCK:
        JOBS[j.id] = j
    threading.Thread(target=run_job, args=(j,), daemon=True).start()
    return j


def get_job(jid):
    with LOCK:
        if jid not in JOBS:
            raise ValueError(f"unknown jobId: {jid}")
        return JOBS[jid]


def wait_for(jobs, wait_ms):
    deadline = time.time() + max(0, wait_ms) / 1000.0
    while time.time() < deadline:
        if all(j.state not in ("starting", "running") for j in jobs):
            return
        time.sleep(0.25)


TOOLS = [
    {
        "name": "claude_start",
        "description": "Start a new Claude Code subagent task in the given workspacePath.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspacePath": {"type": "string", "description": "Absolute path to the working directory."},
                "task": {"type": "string", "description": "Task prompt for Claude Code."},
                "model": {"type": "string", "description": "Optional Claude model alias or id (e.g. sonnet, opus, haiku)."},
                "permissionMode": {
                    "type": "string",
                    "enum": ["acceptEdits", "bypassPermissions", "default", "plan", "dontAsk"],
                    "default": "acceptEdits",
                },
                "effort": {"type": "string", "description": "Effort level (e.g. low, medium, high, xhigh, max)."},
                "disableMcps": {
                    "type": "boolean",
                    "default": True,
                    "description": "Isolate subagent from Claude's external MCP servers for fast startup and no recursion.",
                },
                "wait": {"type": "boolean", "default": False, "description": "Block until completion (up to waitMs)."},
                "waitMs": {"type": "integer", "default": 600000},
            },
            "required": ["workspacePath", "task"],
        },
    },
    {
        "name": "claude_send",
        "description": "Send a follow-up message to an existing Claude Code session (resumes sessionId).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sessionId": {"type": "string"},
                "task": {"type": "string"},
                "workspacePath": {"type": "string"},
                "model": {"type": "string"},
                "permissionMode": {
                    "type": "string",
                    "enum": ["acceptEdits", "bypassPermissions", "default", "plan", "dontAsk"],
                    "default": "acceptEdits",
                },
                "effort": {"type": "string", "description": "Effort level (e.g. low, medium, high, xhigh, max)."},
                "disableMcps": {"type": "boolean", "default": True},
                "wait": {"type": "boolean", "default": False},
                "waitMs": {"type": "integer", "default": 600000},
            },
            "required": ["sessionId", "task"],
        },
    },
    {
        "name": "claude_poll",
        "description": "Poll one or more Claude subagent jobs, optionally waiting up to waitMs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "jobIds": {"type": "array", "items": {"type": "string"}},
                "waitMs": {"type": "integer", "default": 0},
            },
            "required": ["jobIds"],
        },
    },
    {
        "name": "claude_result",
        "description": "Fetch full result, usage, cost, and file changes for a Claude subagent job.",
        "inputSchema": {
            "type": "object",
            "properties": {"jobId": {"type": "string"}},
            "required": ["jobId"],
        },
    },
    {
        "name": "claude_cancel",
        "description": "Cancel a running Claude subagent job.",
        "inputSchema": {
            "type": "object",
            "properties": {"jobId": {"type": "string"}},
            "required": ["jobId"],
        },
    },
    {
        "name": "claude_list",
        "description": "List all Claude subagent jobs in this session.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "claude_info",
        "description": "Show Claude CLI path, version, and job log directory.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def call_tool(name, a):
    if name == "claude_start":
        j = start_job(
            a["workspacePath"],
            a["task"],
            a.get("permissionMode", "acceptEdits"),
            a.get("model") or DEFAULT_MODEL,
            a.get("effort") or DEFAULT_EFFORT,
            a.get("disableMcps", True),
        )
        wait_for([j], a.get("waitMs", 600000) if a.get("wait") else 4000)
        return j.status("full" if a.get("wait") and j.state not in ("starting", "running") else "summary")
    if name == "claude_send":
        prev = next((j for j in reversed(list(JOBS.values())) if j.session_id == a["sessionId"]), None)
        cwd = a.get("workspacePath") or (prev.cwd if prev else None)
        if not cwd:
            raise ValueError("workspacePath is required for a sessionId not started in this server")
        if prev and prev.state in ("starting", "running"):
            raise ValueError(f"session is busy with job {prev.id}")
        j = start_job(
            cwd,
            a["task"],
            a.get("permissionMode", prev.permission_mode if prev else "acceptEdits"),
            a.get("model") or (prev.model if prev else None),
            a.get("effort") or (prev.effort if prev else None),
            a.get("disableMcps", True),
            session_id=a["sessionId"],
        )
        wait_for([j], a.get("waitMs", 600000) if a.get("wait") else 4000)
        return j.status("full" if a.get("wait") and j.state not in ("starting", "running") else "summary")
    if name == "claude_poll":
        js = [get_job(i) for i in a["jobIds"]]
        wait_for(js, a.get("waitMs", 0))
        return {"jobs": [j.status() for j in js]}
    if name == "claude_result":
        return get_job(a["jobId"]).status("full")
    if name == "claude_cancel":
        j = get_job(a["jobId"])
        if j.proc and j.proc.poll() is None:
            subprocess.run(["taskkill", "/PID", str(j.proc.pid), "/T", "/F"], capture_output=True)
            j.state = "cancelled"
        return j.status()
    if name == "claude_list":
        return {
            "jobs": [
                {
                    "jobId": j.id,
                    "sessionId": j.session_id,
                    "state": j.state,
                    "cwd": j.cwd,
                    "elapsedSec": round((j.ended or time.time()) - j.started, 1),
                }
                for j in JOBS.values()
            ]
        }
    if name == "claude_info":
        exe = claude_exe()
        ver = subprocess.run([exe, "--version"], capture_output=True, text=True).stdout.strip()
        return {
            "claudeExe": exe,
            "version": ver,
            "jobLogDir": JOBDIR,
            "defaultModel": DEFAULT_MODEL,
            "defaultEffort": DEFAULT_EFFORT,
        }
    raise ValueError(f"unknown tool: {name}")


def send(msg):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        mid, method, params = req.get("id"), req.get("method"), req.get("params") or {}
        if mid is None:
            continue
        try:
            if method == "initialize":
                res = {
                    "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER,
                    "instructions": (
                        "Claude Code subagent bridge. claude_start -> claude_poll(waitMs) -> claude_result; "
                        "follow-ups via claude_send(sessionId) preserve context."
                    ),
                }
            elif method == "tools/list":
                res = {"tools": TOOLS}
            elif method == "tools/call":
                try:
                    out = call_tool(params["name"], params.get("arguments") or {})
                    res = {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=1)}]}
                except Exception as e:
                    res = {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True}
            elif method == "ping":
                res = {}
            else:
                send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}})
                continue
            send({"jsonrpc": "2.0", "id": mid, "result": res})
        except Exception as e:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": repr(e)}})


if __name__ == "__main__":
    main()

"""codex-workers: a stdio MCP server that lets Claude Code dispatch work to the local Codex CLI
(the one bundled with the Codex desktop app, logged in with the user's ChatGPT account).

Standard library only. Every task runs as `codex exec --json` in the background; follow-ups use
`codex exec resume <threadId>` so the worker keeps its conversation context.

Tools: codex_start, codex_send, codex_poll, codex_result, codex_cancel, codex_list, codex_info
"""
import glob, json, os, shutil, subprocess, sys, threading, time, uuid

SERVER = {"name": "codex-workers", "version": "1.1.0"}
# User rule (2026-11-15): the GPT worker runs gpt-6-luna at medium effort and is used ONLY for asset
# generation (images etc.). Coding work goes to the dsh workers.
DEFAULT_MODEL = os.environ.get("CODEX_WORKER_MODEL", "gpt-6.2-sol")
DEFAULT_EFFORT = os.environ.get("CODEX_WORKER_EFFORT", "medium")
HOME = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("PLUGIN_DATA") or HOME
JOBDIR = os.path.join(DATA_DIR, "jobs")
os.makedirs(JOBDIR, exist_ok=True)
JOBS = {}
LOCK = threading.Lock()


def codex_exe():
    if os.environ.get("CODEX_EXE") and os.path.exists(os.environ["CODEX_EXE"]):
        return os.environ["CODEX_EXE"]
    found = shutil.which("codex")
    if found:
        return found
    la = os.environ.get("LOCALAPPDATA", "")
    cands = []
    if la:
        cands += glob.glob(os.path.join(la, "OpenAI", "Codex", "bin", "*", "codex.exe"))
    cands += glob.glob(os.path.expanduser(r"~\.codex\plugins\.plugin-appserver\codex.exe"))
    cands += glob.glob(os.path.expanduser("~/.codex/plugins/.plugin-appserver/codex"))
    for mac_cand in (
        "/Applications/Codex.app/Contents/Resources/codex",
        "/opt/homebrew/bin/codex",
        "/usr/local/bin/codex",
    ):
        if os.path.exists(mac_cand):
            cands.append(mac_cand)
    if not cands:
        raise RuntimeError("codex CLI not found (is Codex installed? set CODEX_EXE to override)")
    return max(cands, key=os.path.getmtime)


PYLIB = os.path.join(HOME, "pylib")  # pytest etc. for Codex's bundled Python (pip install --target)


def bundled_python():
    """Codex's Windows sandbox may not launch user-installed Pythons; its own bundled Python works."""
    pats = [r"C:\Program Files\WindowsApps\OpenAI.CodexPrimaryRuntime*\dependencies\python\python.exe"]
    c = [p for pat in pats for p in glob.glob(pat)]
    return max(c, key=os.path.getmtime) if c else None


def job_env():
    env = dict(os.environ)
    py = bundled_python()
    if py:
        d = os.path.dirname(py)
        env["PATH"] = os.pathsep.join([d, os.path.join(d, "Scripts"), env.get("PATH", "")])
        env["CODEX_WORKER_PYTHON"] = py
    if os.path.isdir(PYLIB):
        env["PYTHONPATH"] = PYLIB
    env["PYTEST_ADDOPTS"] = "-p no:cacheprovider"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUTF8"] = "1"
    return env


SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache"}


def snapshot(root, limit=20000):
    out = {}
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


def summarize(item):
    t = item.get("type")
    if t == "command_execution":
        return {"type": t, "command": str(item.get("command", ""))[:300], "exit_code": item.get("exit_code"),
                "status": item.get("status")}
    if t == "file_change":
        return {"type": t, "changes": [{"path": c.get("path"), "kind": c.get("kind")} for c in item.get("changes", [])]}
    if t == "agent_message":
        return {"type": t, "text": (item.get("text") or "")[:300]}
    if t in ("error",):
        return {"type": t, "message": str(item.get("message"))[:500]}
    return {"type": t}


class Job:
    def __init__(self, cwd, prompt, sandbox, model, effort, thread_id=None):
        self.id = uuid.uuid4().hex[:12]
        self.cwd, self.prompt, self.sandbox, self.model, self.effort = cwd, prompt, sandbox, model, effort
        self.thread_id = thread_id
        self.state = "starting"
        self.started = time.time()
        self.ended = None
        self.items, self.messages, self.errors = [], [], []
        self.usage = None
        self.proc = None
        self.rc = None
        self.log = os.path.join(JOBDIR, self.id + ".jsonl")
        self.before = snapshot(self.cwd)
        self.changes = None

    def argv(self):
        exe = codex_exe()
        common = ["--json", "--skip-git-repo-check"]
        if self.model:
            common += ["-m", self.model]
        if self.effort:
            common += ["-c", f'model_reasoning_effort="{self.effort}"']
        if self.thread_id:  # follow-up in the same conversation
            return [exe, "exec", "resume", *common, "-c", f'sandbox_mode="{self.sandbox}"', self.thread_id, "-"]
        return [exe, "exec", *common, "-s", self.sandbox, "-C", self.cwd, "-"]

    def run(self):
        try:
            self.proc = subprocess.Popen(self.argv(), cwd=self.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, env=job_env(),
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.proc.stdin.write(self.prompt.encode("utf-8"))
            self.proc.stdin.close()
            self.state = "running"
            err_buf = []
            threading.Thread(target=lambda: err_buf.append(self.proc.stderr.read()), daemon=True).start()
            with open(self.log, "ab") as lg:
                for raw in self.proc.stdout:
                    lg.write(raw)
                    try:
                        ev = json.loads(raw.decode("utf-8", "replace"))
                    except Exception:
                        continue
                    self.on_event(ev)
            self.rc = self.proc.wait()
            if self.rc != 0 and self.state == "running":
                tail = (err_buf[0] if err_buf else b"").decode("utf-8", "replace")[-1500:]
                self.errors.append(f"exit code {self.rc}: {tail}")
                self.state = "failed"
            elif self.state == "running":
                self.state = "completed"
        except Exception as e:
            self.errors.append(repr(e))
            self.state = "failed"
        finally:
            self.ended = time.time()
            try:
                self.changes = diff_snap(self.before, snapshot(self.cwd))
            except Exception as e:
                self.changes = {"error": repr(e)}

    def on_event(self, ev):
        t = ev.get("type")
        if t == "thread.started":
            self.thread_id = ev.get("thread_id")
        elif t == "item.completed":
            it = ev.get("item", {})
            self.items.append(summarize(it))
            if it.get("type") == "agent_message":
                self.messages.append(it.get("text") or "")
        elif t == "turn.completed":
            self.usage = ev.get("usage")
        elif t in ("turn.failed", "error"):
            self.errors.append(json.dumps(ev, ensure_ascii=False)[:1500])
            if t == "turn.failed":
                self.state = "failed"

    def status(self, detail="summary"):
        if self.changes is not None:
            changed = self.changes
        else:  # still running: report what Codex's own file_change events said so far
            changed = sorted({c["path"] for i in self.items if i["type"] == "file_change" for c in i["changes"] if c.get("path")})
        cmds = [i for i in self.items if i["type"] == "command_execution"]
        d = {"jobId": self.id, "threadId": self.thread_id, "state": self.state, "cwd": self.cwd,
             "sandbox": self.sandbox, "model": self.model or "(config default)",
             "elapsedSec": round((self.ended or time.time()) - self.started, 1),
             "commandCount": len(cmds), "failedCommands": sum(1 for c in cmds if c.get("exit_code") not in (0, None)),
             "changedFiles": changed, "usage": self.usage, "errors": self.errors}
        last = self.messages[-1] if self.messages else ""
        if detail == "summary":
            d["lastMessage"] = last[:600] + ("…[truncated; use codex_result]" if len(last) > 600 else "")
        else:
            d["finalMessage"] = last
            d["commands"] = cmds[-40:]
        return d


def start_job(cwd, prompt, sandbox, model, effort, thread_id=None):
    if not os.path.isdir(cwd):
        raise ValueError(f"workspacePath does not exist: {cwd}")
    if sandbox not in ("read-only", "workspace-write"):
        raise ValueError("sandbox must be read-only or workspace-write (danger-full-access is not offered)")
    j = Job(os.path.abspath(cwd), prompt, sandbox, model or DEFAULT_MODEL, effort or DEFAULT_EFFORT, thread_id)
    with LOCK:
        JOBS[j.id] = j
    threading.Thread(target=j.run, daemon=True).start()
    return j


def wait_for(jobs, wait_ms):
    end = time.time() + min(max(wait_ms, 0), 600000) / 1000
    while time.time() < end and any(j.state in ("starting", "running") for j in jobs):
        time.sleep(1)


def get(job_id):
    j = JOBS.get(job_id)
    if not j:
        raise ValueError(f"unknown jobId {job_id} (jobs live only while this MCP server runs)")
    return j


TOOLS = [
    {"name": "codex_start",
     "description": "Start a NEW Codex (ChatGPT) worker task in a folder. Policy: use this worker ONLY for asset generation (images, icons, sprites, textures and similar); coding work goes to the dsh workers. Default model gpt-6-luna, reasoning medium. Runs `codex exec` in the background and returns a jobId and (once known) threadId immediately. Observe with codex_poll, read with codex_result. Set wait=true to block until it finishes (up to waitMs).",
     "inputSchema": {"type": "object", "required": ["workspacePath", "task"], "properties": {
         "workspacePath": {"type": "string", "description": "Absolute folder the worker operates in."},
         "task": {"type": "string", "description": "Full instructions for the worker."},
         "sandbox": {"type": "string", "enum": ["read-only", "workspace-write"], "default": "workspace-write"},
         "model": {"type": "string", "description": "Optional Codex/GPT model override (e.g. gpt-6.2-sol, gpt-6.2-astra, gpt-6.1-terra, gpt-6-luna)."},
         "reasoningEffort": {"type": "string", "description": "Reasoning effort (e.g. minimal, low, medium, high, xhigh, max, ultra)."},
         "wait": {"type": "boolean", "default": False},
         "waitMs": {"type": "number", "default": 600000}}}},
    {"name": "codex_send",
     "description": "Send a follow-up message to an existing Codex conversation (by threadId from codex_start/codex_poll). The worker keeps its earlier context. Returns a new jobId.",
     "inputSchema": {"type": "object", "required": ["threadId", "task"], "properties": {
         "threadId": {"type": "string"}, "task": {"type": "string"},
         "workspacePath": {"type": "string", "description": "Defaults to the folder of the thread's previous job."},
         "sandbox": {"type": "string", "enum": ["read-only", "workspace-write"], "default": "workspace-write"},
         "model": {"type": "string"}, "reasoningEffort": {"type": "string"},
         "wait": {"type": "boolean", "default": False}, "waitMs": {"type": "number", "default": 600000}}}},
    {"name": "codex_poll",
     "description": "Status of one or more jobs: state (running/completed/failed/cancelled), threadId, elapsed seconds, commands run, changed files, token usage, last message (truncated). waitMs>0 blocks until all listed jobs finish or the wait ends.",
     "inputSchema": {"type": "object", "required": ["jobIds"], "properties": {
         "jobIds": {"type": "array", "items": {"type": "string"}}, "waitMs": {"type": "number", "default": 0}}}},
    {"name": "codex_result",
     "description": "Full result of a job: final message (untruncated), recent commands with exit codes, changed files, usage, errors.",
     "inputSchema": {"type": "object", "required": ["jobId"], "properties": {"jobId": {"type": "string"}}}},
    {"name": "codex_cancel", "description": "Stop a running job (kills the codex process).",
     "inputSchema": {"type": "object", "required": ["jobId"], "properties": {"jobId": {"type": "string"}}}},
    {"name": "codex_list", "description": "List jobs started by this server in this Claude Code session.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "codex_info", "description": "Show which codex.exe is used, its version, and the configured default model.",
     "inputSchema": {"type": "object", "properties": {}}},
]


def call_tool(name, a):
    if name == "codex_start":
        j = start_job(a["workspacePath"], a["task"], a.get("sandbox", "workspace-write"), a.get("model"), a.get("reasoningEffort"))
        if a.get("wait"):
            wait_for([j], a.get("waitMs", 600000))
        else:
            wait_for([j], 4000)  # give it a moment to report threadId
        return j.status("full" if a.get("wait") and j.state != "running" else "summary")
    if name == "codex_send":
        prev = next((j for j in reversed(list(JOBS.values())) if j.thread_id == a["threadId"]), None)
        cwd = a.get("workspacePath") or (prev.cwd if prev else None)
        if not cwd:
            raise ValueError("workspacePath is required for a thread not started in this session")
        if prev and prev.state in ("starting", "running"):
            raise ValueError(f"thread is busy with job {prev.id}; wait for it or cancel it first")
        j = start_job(cwd, a["task"], a.get("sandbox", "workspace-write"), a.get("model") or (prev.model if prev else None),
                      a.get("reasoningEffort") or (prev.effort if prev else None), thread_id=a["threadId"])
        if a.get("wait"):
            wait_for([j], a.get("waitMs", 600000))
        return j.status("full" if a.get("wait") and j.state != "running" else "summary")
    if name == "codex_poll":
        js = [get(i) for i in a["jobIds"]]
        wait_for(js, a.get("waitMs", 0))
        return {"jobs": [j.status() for j in js]}
    if name == "codex_result":
        return get(a["jobId"]).status("full")
    if name == "codex_cancel":
        j = get(a["jobId"])
        if j.proc and j.proc.poll() is None:
            subprocess.run(["taskkill", "/PID", str(j.proc.pid), "/T", "/F"], capture_output=True)
            j.state = "cancelled"
        return j.status()
    if name == "codex_list":
        return {"jobs": [{"jobId": j.id, "threadId": j.thread_id, "state": j.state, "cwd": j.cwd,
                          "elapsedSec": round((j.ended or time.time()) - j.started, 1)} for j in JOBS.values()]}
    if name == "codex_info":
        exe = codex_exe()
        ver = subprocess.run([exe, "--version"], capture_output=True, text=True).stdout.strip()
        model = None
        try:
            for line in open(os.path.expanduser("~/.codex/config.toml"), encoding="utf-8"):
                if line.startswith("model ="):
                    model = line.split("=", 1)[1].strip().strip('"')
                    break
        except Exception:
            pass
        return {"codexExe": exe, "version": ver, "defaultModel": model, "jobLogDir": JOBDIR,
                "workerPython": bundled_python(), "workerPythonPath": PYLIB if os.path.isdir(PYLIB) else None,
                "note": "Jobs get PATH with Codex's bundled Python first, PYTHONPATH=pylib (pytest), PYTEST_ADDOPTS=-p no:cacheprovider."}
    raise ValueError(f"unknown tool {name}")


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
            continue  # notification
        try:
            if method == "initialize":
                res = {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                       "capabilities": {"tools": {}}, "serverInfo": SERVER,
                       "instructions": "Codex (ChatGPT) worker bridge, for ASSET GENERATION ONLY (images etc.; user policy, model gpt-6-luna at medium). codex_start → codex_poll(waitMs) → codex_result; "
                                       "follow-ups via codex_send(threadId) keep context. Sandbox is read-only or workspace-write only."}
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

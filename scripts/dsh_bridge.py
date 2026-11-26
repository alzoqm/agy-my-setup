"""dsh_bridge: stdio-to-Streamable-HTTP MCP bridge for DeepSeek Harness Desktop (dsh-rice-on-a-stick).

Standard library only. Connects to http://127.0.0.1:5642/mcp with Bearer auth,
auto-launching DeepSeek Harness Desktop if the port is not yet listening.
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

DSH_URL = os.environ.get("DSH_MCP_URL", "http://127.0.0.1:5642/mcp")
DSH_TOKEN = os.environ.get("DSH_MCP_TOKEN", "")
DSH_HOST = os.environ.get("DSH_HOST", "127.0.0.1")
DSH_PORT = int(os.environ.get("DSH_PORT", "5642"))
DSH_EXE = os.environ.get(
    "DSH_EXE",
    os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local")),
        "Programs",
        "DeepSeek Harness",
        "DeepSeek Harness.exe",
    ),
)

SESSION_ID = None


def port_open(host, port, timeout=0.4):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_dsh_running():
    if port_open(DSH_HOST, DSH_PORT):
        return
    if not os.path.exists(DSH_EXE):
        raise RuntimeError(f"DeepSeek Harness.exe not found at {DSH_EXE}")
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        [DSH_EXE],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    deadline = time.time() + 25.0
    while time.time() < deadline:
        if port_open(DSH_HOST, DSH_PORT):
            time.sleep(0.5)
            return
        time.sleep(0.5)
    raise RuntimeError(f"DeepSeek Harness did not open port {DSH_PORT} within 25s")


def parse_mcp_response(raw_bytes, content_type):
    text = raw_bytes.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    if "text/event-stream" in (content_type or "") or text.startswith("event:") or text.startswith("data:"):
        last_data = None
        for line in text.splitlines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload:
                    last_data = json.loads(payload)
        return last_data
    return json.loads(text)


def post_upstream(payload, is_init=False):
    global SESSION_ID
    ensure_dsh_running()
    headers = {
        "Authorization": f"Bearer {DSH_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if SESSION_ID and not is_init:
        headers["mcp-session-id"] = SESSION_ID
    req = urllib.request.Request(
        DSH_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            sid = resp.headers.get("mcp-session-id")
            if sid:
                SESSION_ID = sid
            return parse_mcp_response(resp.read(), resp.headers.get("Content-Type", ""))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if e.code in (400, 404) and not is_init and SESSION_ID:
            SESSION_ID = None
            init_upstream()
            return post_upstream(payload, is_init=False)
        raise RuntimeError(f"HTTP {e.code} from dsh-rice-on-a-stick: {body[:500]}")


def init_upstream():
    res = post_upstream(
        {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "antigravity-dsh-bridge", "version": "1.0.0"},
            },
        },
        is_init=True,
    )
    try:
        post_upstream({"jsonrpc": "2.0", "method": "notifications/initialized"}, is_init=False)
    except Exception:
        pass
    return res


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
        mid = req.get("id")
        method = req.get("method")

        if mid is None:
            if SESSION_ID and method != "notifications/initialized":
                try:
                    post_upstream(req)
                except Exception:
                    pass
            continue

        try:
            if method == "initialize":
                upstream = init_upstream()
                if upstream and "result" in upstream:
                    send({"jsonrpc": "2.0", "id": mid, "result": upstream["result"]})
                else:
                    send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": "upstream init failed"}})
                continue

            if not SESSION_ID:
                init_upstream()

            upstream = post_upstream(req)
            if upstream is None:
                send({"jsonrpc": "2.0", "id": mid, "result": {}})
            elif "error" in upstream:
                send({"jsonrpc": "2.0", "id": mid, "error": upstream["error"]})
            else:
                send({"jsonrpc": "2.0", "id": mid, "result": upstream.get("result", {})})
        except Exception as e:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": repr(e)}})


if __name__ == "__main__":
    main()

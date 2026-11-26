import base64
import hashlib
import html as htmllib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ["PLUGIN_DATA"]) if os.environ.get("PLUGIN_DATA") else BASE_DIR
CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _http_get(url: str, timeout: int = 10) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        ctype = resp.headers.get("Content-Type", "application/octet-stream")
        return resp.read(), ctype


def search_images(query: str, limit: int = 3) -> dict:
    limit = max(1, min(int(limit or 3), 6))
    encoded = urllib.parse.quote(query)
    search_url = f"https://www.bing.com/images/search?q={encoded}&form=HDRSC2"
    raw_bytes, _ = _http_get(search_url, timeout=12)
    raw_html = raw_bytes.decode("utf-8", "ignore")

    matches = re.findall(r'm="(\{[^"]+\})"', raw_html)
    results = []
    seen_urls = set()

    for m in matches:
        if len(results) >= limit:
            break
        unescaped = htmllib.unescape(m)
        turl_m = re.search(r'"turl":"([^"]+)"', unescaped)
        murl_m = re.search(r'"murl":"([^"]+)"', unescaped)
        purl_m = re.search(r'"purl":"([^"]+)"', unescaped)
        title_m = re.search(r'"t":"([^"]+)"', unescaped)

        img_url = (turl_m.group(1) if turl_m else None) or (
            murl_m.group(1) if murl_m else None
        )
        if not img_url or img_url in seen_urls:
            continue
        seen_urls.add(img_url)

        try:
            img_bytes, ctype = _http_get(img_url, timeout=8)
            if not ctype.startswith("image/") or len(img_bytes) < 1024:
                continue
            if len(img_bytes) > 600_000:
                continue
        except Exception:
            continue

        ext = "jpg"
        if "png" in ctype:
            ext = "png"
        elif "webp" in ctype:
            ext = "webp"

        image_id = hashlib.sha256(img_url.encode("utf-8")).hexdigest()[:12]
        cache_path = CACHE_DIR / f"{image_id}.{ext}"
        cache_path.write_bytes(img_bytes)

        meta_path = CACHE_DIR / f"{image_id}.json"
        meta = {
            "image_id": image_id,
            "title": title_m.group(1) if title_m else query,
            "source_url": purl_m.group(1) if purl_m else img_url,
            "mime_type": ctype.split(";")[0].strip(),
            "file_path": str(cache_path),
            "size_bytes": len(img_bytes),
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        results.append(meta)

    return {"query": query, "count": len(results), "images": results}


def _load_cached_image_data_uri(image_id: str) -> dict | None:
    meta_path = CACHE_DIR / f"{image_id}.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    img_path = Path(meta["file_path"])
    if not img_path.exists():
        return None
    b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
    mime = meta.get("mime_type", "image/jpeg")
    return {
        "image_id": image_id,
        "title": meta.get("title", ""),
        "source_url": meta.get("source_url", ""),
        "data_uri": f"data:{mime};base64,{b64}",
    }


def render_editorial_widget(
    output_path: str,
    title: str = "",
    subtitle: str = "",
    image_ids: list[str] | None = None,
    spec_card: dict | None = None,
    quadrants: list[dict] | None = None,
    timeline: list[dict] | None = None,
) -> dict:
    images = []
    for iid in image_ids or []:
        loaded = _load_cached_image_data_uri(iid)
        if loaded:
            images.append(loaded)

    esc = htmllib.escape

    header_html = ""
    if title or subtitle:
        header_html = f"""
        <div class="pb-2 border-b border-[var(--card-border)]">
          {f'<div class="text-sm font-semibold text-[var(--foreground)]">{esc(title)}</div>' if title else ''}
          {f'<div class="text-xs text-[var(--muted-foreground)] mt-0.5">{esc(subtitle)}</div>' if subtitle else ''}
        </div>"""

    gallery_html = ""
    if images:
        cols = "grid-cols-1" if len(images) == 1 else ("grid-cols-2" if len(images) == 2 else "grid-cols-3")
        img_cls = (
            "w-full max-h-64 object-contain bg-black/5 dark:bg-white/5"
            if len(images) == 1
            else "w-full h-36 object-cover"
        )
        cards = []
        for idx, img in enumerate(images):
            short_title = esc(img["title"][:48] + ("…" if len(img["title"]) > 48 else ""))
            cards.append(f"""
            <div class="group relative rounded-lg overflow-hidden border border-[var(--card-border)] bg-[var(--card)]">
              <img src="{img['data_uri']}" alt="{short_title}" class="{img_cls}" />
              <div class="px-2 py-1 text-[11px] text-[var(--muted-foreground)] truncate" title="{esc(img['title'])}">{short_title}</div>
            </div>""")
        gallery_html = f'<div class="grid {cols} gap-2">{"".join(cards)}</div>'

    spec_html = ""
    if spec_card and spec_card.get("rows"):
        rows_html = "".join(
            f"""<div class="flex items-start justify-between gap-3 py-1.5 border-b border-[var(--card-border)] last:border-b-0">
              <span class="text-[var(--muted-foreground)] shrink-0">{esc(str(r.get("label", "")))}</span>
              <span class="text-right font-medium text-[var(--foreground)]">{esc(str(r.get("value", "")))}</span>
            </div>"""
            for r in spec_card["rows"]
        )
        sc_title = esc(str(spec_card.get("title", "")))
        sc_sub = esc(str(spec_card.get("subtitle", "")))
        spec_html = f"""
        <div class="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-3 text-xs">
          {f'<div class="font-semibold text-[var(--foreground)]">{sc_title}</div>' if sc_title else ''}
          {f'<div class="text-[11px] text-[var(--muted-foreground)] mb-2">{sc_sub}</div>' if sc_sub else '<div class="mb-1"></div>'}
          <div>{rows_html}</div>
        </div>"""

    quad_html = ""
    if quadrants:
        q_cards = "".join(
            f"""<div class="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-2.5 text-xs">
              <div class="font-semibold text-[var(--primary)]">{esc(str(q.get("title", "")))}</div>
              <div class="text-[var(--muted-foreground)] mt-0.5 leading-relaxed">{esc(str(q.get("desc", "")))}</div>
            </div>"""
            for q in quadrants[:4]
        )
        quad_html = f'<div class="grid grid-cols-2 gap-2">{q_cards}</div>'

    time_html = ""
    if timeline:
        t_rows = "".join(
            f"""<div class="flex items-start gap-2.5 text-xs">
              <span class="mt-1 w-2 h-2 rounded-full bg-[var(--primary)] shrink-0"></span>
              <div>
                <span class="font-semibold text-[var(--foreground)]">{esc(str(t.get("step", "")))}</span>
                <span class="text-[var(--muted-foreground)]"> — {esc(str(t.get("desc", "")))}</span>
              </div>
            </div>"""
            for t in timeline
        )
        time_html = f'<div class="rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-3 space-y-2">{t_rows}</div>'

    doc = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
</head>
<body class="bg-transparent text-[var(--foreground)] antialiased p-0 m-0">
  <div class="py-2 space-y-2.5">
    {header_html}
    {gallery_html}
    {spec_html}
    {quad_html}
    {time_html}
  </div>
</body>
</html>
"""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")

    return {
        "status": "ok",
        "output_path": str(out),
        "embedded_images": len(images),
    }


TOOLS = [
    {
        "name": "search_images",
        "description": (
            "Search the web for relevant images (no API key needed) and cache thumbnails locally. "
            "Returns lightweight image_id metadata to pass into render_editorial_widget."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Image search query"},
                "limit": {"type": "integer", "description": "Number of images (1-6, default 3)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "render_editorial_widget",
        "description": (
            "Generate a ChatGPT-style editorial HTML widget (image gallery, spec card, 4-quadrant card, "
            "or timeline) into output_path (inside the conversation artifact directory) with cached images embedded."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "output_path": {"type": "string", "description": "Absolute path to save the .html file"},
                "title": {"type": "string"},
                "subtitle": {"type": "string"},
                "image_ids": {"type": "array", "items": {"type": "string"}},
                "spec_card": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "subtitle": {"type": "string"},
                        "rows": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "value": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                "quadrants": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "desc": {"type": "string"},
                        },
                    },
                },
                "timeline": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step": {"type": "string"},
                            "desc": {"type": "string"},
                        },
                    },
                },
            },
            "required": ["output_path"],
        },
    },
]


def _send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = req.get("method")
        req_id = req.get("id")
        params = req.get("params") or {}

        if method == "initialize":
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "editorial-media", "version": "1.0.0"},
                    },
                }
            )
        elif method == "notifications/initialized":
            continue
        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": req_id, "result": {}})
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            try:
                if name == "search_images":
                    out = search_images(args["query"], args.get("limit", 3))
                elif name == "render_editorial_widget":
                    out = render_editorial_widget(**args)
                else:
                    raise ValueError(f"Unknown tool: {name}")
                _send(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {"type": "text", "text": json.dumps(out, ensure_ascii=False)}
                            ]
                        },
                    }
                )
            except Exception as exc:
                _send(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "isError": True,
                            "content": [{"type": "text", "text": str(exc)}],
                        },
                    }
                )
        elif req_id is not None:
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yotta_learn_view.py — 元习知识库本地图形化管理台（yotta-learn view）。

零依赖（Python 3.8+ 标准库）：http.server + assets/view.html（单一真源）。
安全壳（对齐元忆 / 元阁面板口径）：
- 仅绑定 127.0.0.1；Host / Origin / Sec-Fetch-Site 校验；
- 页面内嵌本机会话令牌；写操作必须携带 X-Yotta-View-Token（timing-safe 比较）；
- 破坏性动作需确认串；请求体上限 64 KB；写操作串行化；
- 严格 CSP / no-store / X-Frame-Options: DENY；零远程资源；
- 所有写操作走 yotta_kb 内核（与 CLI 同一真源）并写审计。

启动：yotta-learn view [--port 8791] [--dir <KB>]
"""

import hmac
import json
import os
import re
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import yotta_kb  # noqa: E402
import yotta_kb_index  # noqa: E402

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8791
TOKEN_HEADER = "x-yotta-view-token"
BODY_LIMIT = 64 * 1024
TOKEN_PLACEHOLDER = "__YOTTA_VIEW_TOKEN__"
VIEW_VERSION = "0.4.0"
AUDIT_TAIL_LIMIT = 200

CONFIRM = {
    "entry_deprecate": "entry-deprecate",
    "index_rebuild": "index-rebuild",
    "location_set": "location-set",
    "location_move": "location-move",
    "trash_purge": "trash-purge",
    "snapshot_restore": "snapshot-restore",
    "review_force": "review-force",
}

CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
       "connect-src 'self'; img-src 'self' data:; font-src 'self'; base-uri 'none'; "
       "form-action 'none'; frame-ancestors 'none'")


# ── 安全壳 ──────────────────────────────────────────────────────────────────

def host_allowed(host_header, port):
    """Host 头只允许 loopback（127.0.0.1 / localhost / [::1]，端口须一致）。"""
    host = str(host_header or "").strip().lower()
    if not host:
        return False
    if host.startswith("["):
        name, _, rest = host.partition("]")
        name = name + "]"
    else:
        name, _, rest = host.partition(":")
    if name not in ("127.0.0.1", "localhost", "[::1]"):
        return False
    if rest:
        return rest.isdigit() and int(rest) == int(port)
    return True


def origin_allowed(origin, host_header):
    """Origin（浏览器跨域标记）必须与请求 Host 严格一致；无 Origin 放行。"""
    if not origin:
        return True
    try:
        parsed = urlparse(str(origin))
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    origin_host = (parsed.netloc or "").lower()
    request_host = str(host_header or "").strip().lower()
    return bool(origin_host) and origin_host == request_host


def fetch_site_allowed(value):
    """Sec-Fetch-Site 只允许 same-origin / none（缺省放行，兼容旧客户端）。"""
    return str(value or "").strip().lower() in ("", "same-origin", "none")


def token_allowed(provided, token):
    if not provided or not token:
        return False
    return hmac.compare_digest(str(provided), str(token))


def _read_jsonl_tail(path, limit):
    p = Path(path)
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-max(1, int(limit)):]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


# ── 上下文与只读负载 ────────────────────────────────────────────────────────

class ViewContext:
    def __init__(self, explicit_dir=None, token="", html=""):
        self.explicit_dir = explicit_dir
        self.token = token
        self.html = html
        self.lock = threading.Lock()

    def root(self):
        root, source = yotta_kb.resolve_kb_root(self.explicit_dir)
        yotta_kb.load_kb(root)
        return root, source


def overview_payload(ctx):
    root, source = ctx.root()
    stats = yotta_kb_index.stats(root)
    report = yotta_kb.doctor(root)
    return {
        "root": str(root), "origin": source, "version": VIEW_VERSION,
        "stats": stats,
        "doctor": {"errors": report["errors"], "warnings": report["warnings"],
                   "checks": report["checks"]},
        "audit": _read_jsonl_tail(yotta_kb.audit_path(root), 8),
    }


def categories_payload(ctx):
    root, source = ctx.root()
    cats = yotta_kb.list_categories(root)
    return {"root": str(root), "origin": source, "count": len(cats), "categories": cats}


def entries_payload(ctx, query):
    root, source = ctx.root()
    category = (query.get("category") or [""])[0].strip() or None
    if category:
        category = yotta_kb.resolve_category(root, category)["slug"]
    status = (query.get("status") or [""])[0].strip()
    tag = (query.get("tag") or [""])[0].strip().lower()
    limit = int((query.get("limit") or ["200"])[0] or 200)
    entries = []
    for entry in yotta_kb.iter_entries(root, category=category):
        if status and entry.status != status:
            continue
        if tag and tag not in [t.lower() for t in entry.tags]:
            continue
        entries.append(entry)
    entries.sort(key=lambda e: (e.updated, e.id), reverse=True)
    if limit > 0:
        entries = entries[:limit]
    return {"root": str(root), "origin": source, "count": len(entries),
            "entries": [e.to_dict() for e in entries]}


def search_payload(ctx, query):
    root, source = ctx.root()
    q = (query.get("q") or [""])[0].strip()
    if not q:
        raise yotta_kb.KbUsageError("搜索需要 q 参数（关键词）")
    statuses = None
    status = (query.get("status") or [""])[0].strip()
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
    result = yotta_kb_index.query(
        root, q, category=((query.get("category") or [""])[0].strip() or None),
        statuses=statuses, tags=[t.strip() for t in (query.get("tag") or []) if t.strip()],
        limit=int((query.get("limit") or ["20"])[0] or 20),
        include_draft=(query.get("include_draft") or ["0"])[0] in ("1", "true", "yes"),
        include_deprecated=(query.get("include_deprecated") or ["0"])[0] in ("1", "true", "yes"))
    result["root"] = str(root)
    result["origin"] = source
    return result


def entry_payload(ctx, query):
    root, source = ctx.root()
    eid = (query.get("id") or [""])[0].strip()
    if not eid:
        raise yotta_kb.KbUsageError("需要 id 参数（KB-YYYYMMDD-XXX）")
    entry = yotta_kb.find_entry(root, eid)
    if entry is None:
        raise yotta_kb.KbNotFound("未找到条目：%s" % eid)
    data = entry.to_dict(include_body=True)
    data["path"] = str(entry.path)
    data["root"] = str(root)
    data["origin"] = source
    return data


def location_payload(ctx):
    info = yotta_kb.location_info(ctx.explicit_dir)
    return info


def ops_payload(ctx, query):
    root, source = ctx.root()
    backup_dir = (query.get("backup_dir") or [""])[0].strip() or None
    report = yotta_kb.doctor(root, backup_dir=backup_dir)
    return {
        "root": str(root), "origin": source,
        "doctor": {"errors": report["errors"], "warnings": report["warnings"],
                   "checks": report["checks"]},
        "trash": yotta_kb.list_trash(root),
        "snapshots": yotta_kb.list_snapshots(root),
        "backup_dir": backup_dir,
        "backups": yotta_kb.backup_list(backup_dir) if backup_dir else [],
    }


def audit_payload(ctx, query):
    root, source = ctx.root()
    limit = int((query.get("limit") or ["50"])[0] or 50)
    limit = max(1, min(limit, AUDIT_TAIL_LIMIT))
    return {"root": str(root), "origin": source, "limit": limit,
            "records": _read_jsonl_tail(yotta_kb.audit_path(root), limit)}


# ── 写操作（内核同一真源 + 审计） ───────────────────────────────────────────

def _need_confirm(body, key):
    if str(body.get("confirm") or "") != CONFIRM[key]:
        raise yotta_kb.KbUsageError('确认串不匹配（需要 "%s"）' % CONFIRM[key])


def execute_action(ctx, body):
    if not isinstance(body, dict):
        raise yotta_kb.KbUsageError("请求体必须是 JSON 对象")
    action = str(body.get("action") or "").strip()
    root, _source = ctx.root()
    actor = yotta_kb.resolve_actor("view")
    target = ""
    detail = {}

    if action == "category.create":
        slug = str(body.get("slug") or "").strip()
        name = str(body.get("name") or "").strip()
        description = str(body.get("description") or "").strip()
        aliases = body.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [a.strip() for a in aliases.split(",") if a.strip()]
        cat = yotta_kb.create_category(root, slug, name, description, aliases, actor)
        target = cat["slug"]
        detail = {"name": cat["name"]}
        result = {"slug": cat["slug"], "name": cat["name"]}

    elif action == "entry.add":
        tags = body.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        entry = yotta_kb.add_entry(
            root, str(body.get("category") or "").strip(),
            str(body.get("title") or "").strip(), body.get("message") or "",
            tags, body.get("source") or "", body.get("evidence") or "",
            str(body.get("confidence") or "medium"), actor)
        text = "\n".join([entry.title, " ".join(entry.tags), entry.body])
        target = entry.id
        detail = {"category": entry.category}
        result = {"id": entry.id, "status": entry.status,
                  "sensitive": yotta_kb.scan_sensitive(text),
                  "similar": yotta_kb.similar_titles(root, entry)}

    elif action == "entry.review":
        eid = str(body.get("id") or "").strip()
        decision = str(body.get("decision") or "").strip().lower()
        force = bool(body.get("force"))
        if force:
            _need_confirm(body, "review_force")
        entry, extra = yotta_kb.review_entry(
            root, eid, decision, body.get("note") or "",
            body.get("evidence") or "", actor, force=force)
        target = entry.id
        detail = {"decision": decision, "force": force}
        result = {"id": entry.id, "status": entry.status,
                  "findings": extra.get("findings") or [],
                  "similar": extra.get("similar") or []}

    elif action == "entry.update":
        eid = str(body.get("id") or "").strip()
        changes = {}
        for key in ("title", "message", "source", "evidence", "confidence"):
            if body.get(key) is not None:
                changes[key] = body[key]
        if body.get("tags") is not None:
            tags = body.get("tags")
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            changes["tags"] = tags
        if not changes:
            raise yotta_kb.KbUsageError("至少需要一个可更新字段")
        entry = yotta_kb.update_entry(root, eid, changes, actor)
        target = entry.id
        detail = {"fields": sorted(changes.keys())}
        result = {"id": entry.id, "updated": sorted(changes.keys())}

    elif action == "entry.deprecate":
        _need_confirm(body, "entry_deprecate")
        entry = yotta_kb.deprecate_entry(root, str(body.get("id") or "").strip(),
                                         body.get("reason") or "", actor)
        target = entry.id
        result = {"id": entry.id, "status": entry.status}

    elif action == "index.rebuild":
        _need_confirm(body, "index_rebuild")
        with yotta_kb.KbLock(root):
            stats = yotta_kb_index.rebuild_all(root)
        target = str(root)
        detail = {"entries": stats["total_entries"], "terms": stats["terms"]}
        result = {"total_entries": stats["total_entries"], "terms": stats["terms"]}

    elif action == "location.set":
        move = bool(body.get("move"))
        _need_confirm(body, "location_move" if move else "location_set")
        target_dir = str(body.get("dir") or "").strip()
        if not target_dir:
            raise yotta_kb.KbUsageError("location.set 需要 dir 参数（目标位置）")
        if not move and not yotta_kb.is_initialized(Path(target_dir).expanduser().resolve()):
            raise yotta_kb.KbIntegrityError(
                "目标位置未初始化；如要迁往新位置请使用迁移（move=true）")
        current_root, _src = yotta_kb.resolve_kb_root(ctx.explicit_dir)
        result = yotta_kb.set_location(target_dir, move=move, current_root=current_root)
        ctx.explicit_dir = result["target"]  # 会话内立即切到新位置
        root = Path(result["target"]).resolve()  # 迁移后的审计写入新库
        target = result["target"]
        detail = {"move": move, "from": result["source"]}

    elif action == "trash.purge":
        _need_confirm(body, "trash_purge")
        days = int(body.get("days") or yotta_kb.TRASH_RETENTION_DAYS)
        result = yotta_kb.purge_trash(root, actor, days=days,
                                      purge_all=bool(body.get("all")))
        target = str(root)
        detail = dict(result)

    elif action == "snapshot.restore":
        _need_confirm(body, "snapshot_restore")
        name = yotta_kb.restore_snapshot(root, str(body.get("name") or "").strip(), actor)
        target = name
        result = {"restored": name}

    elif action == "backup.create":
        out = str(body.get("out") or "").strip()
        if not out:
            raise yotta_kb.KbUsageError("backup.create 需要 out 参数（独立备份目录）")
        dest, manifest = yotta_kb.backup_create(root, out, actor)
        target = str(dest)
        detail = {"entries": manifest["entries"]}
        result = {"dest": str(dest), "entries": manifest["entries"],
                  "files": len(manifest["files"])}

    else:
        raise yotta_kb.KbUsageError("未知操作：%s" % (action or "(空)"))

    yotta_kb.audit(root, actor, "view." + action, target, "ok", detail)
    result["action"] = action
    return result


# ── HTTP ────────────────────────────────────────────────────────────────────

def _kb_http_code(exc):
    if isinstance(exc, yotta_kb.KbUsageError):
        return 400
    if isinstance(exc, yotta_kb.KbGateError):
        return 409
    if isinstance(exc, yotta_kb.KbIntegrityError):
        return 409
    if isinstance(exc, yotta_kb.KbNotFound):
        return 404
    return 500


class ViewHandler(BaseHTTPRequestHandler):
    server_version = "yotta-learn-view/" + VIEW_VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: A003
        if os.environ.get("YOTTA_LEARN_VIEW_DEBUG"):
            sys.stderr.write("[view] " + (fmt % args) + "\n")

    # -- 基础输出 --

    def _send(self, code, body, content_type, extra_headers=None):
        data = body if isinstance(body, bytes) else str(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(data)
            except OSError:
                pass

    def _json(self, code, payload):
        self._send(code, json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")

    def _text(self, code, text):
        self._send(code, text, "text/plain; charset=utf-8")

    def _html(self, html):
        self._send(200, html, "text/html; charset=utf-8", {
            "Content-Security-Policy": CSP,
            "X-Frame-Options": "DENY",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        })

    # -- 安全壳 --

    def _guard(self):
        ctx = self.server.view_ctx  # type: ignore[attr-defined]
        if not host_allowed(self.headers.get("Host"), self.server.server_port):
            self._text(403, "forbidden")
            return False
        if not origin_allowed(self.headers.get("Origin"), self.headers.get("Host")):
            self._text(403, "forbidden")
            return False
        if not fetch_site_allowed(self.headers.get("Sec-Fetch-Site")):
            self._text(403, "forbidden")
            return False
        return ctx

    # -- 路由 --

    def do_GET(self):  # noqa: N802
        ctx = self._guard()
        if not ctx:
            return
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/":
            return self._html(ctx.html)
        if path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        routes = {
            "/api/overview": lambda: overview_payload(ctx),
            "/api/categories": lambda: categories_payload(ctx),
            "/api/entries": lambda: entries_payload(ctx, query),
            "/api/search": lambda: search_payload(ctx, query),
            "/api/entry": lambda: entry_payload(ctx, query),
            "/api/location": lambda: location_payload(ctx),
            "/api/ops": lambda: ops_payload(ctx, query),
            "/api/audit": lambda: audit_payload(ctx, query),
        }
        handler = routes.get(path)
        if handler is None:
            return self._text(404, "not found")
        try:
            return self._json(200, handler())
        except yotta_kb.KbError as exc:
            return self._json(_kb_http_code(exc), {"error": exc.message, "code": exc.code})
        except Exception as exc:  # noqa: BLE001
            return self._json(500, {"error": str(exc)})

    def do_POST(self):  # noqa: N802
        ctx = self._guard()
        if not ctx:
            return
        parsed = urlparse(self.path)
        if parsed.path != "/api/action":
            return self._text(404, "not found")
        if not token_allowed(self.headers.get(TOKEN_HEADER), ctx.token):
            return self._json(403, {"error": "写操作需要有效的本机会话令牌；"
                                             "请从 yotta-learn view 页面操作。"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json(400, {"error": "Content-Length 非法"})
        if length <= 0:
            return self._json(400, {"error": "请求体为空"})
        if length > BODY_LIMIT:
            # 丢弃超量请求体（上限 1 MB），避免污染 keep-alive 连接
            remaining = min(length, 1 << 20)
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 65536))
                if not chunk:
                    break
                remaining -= len(chunk)
            return self._json(413, {"error": "请求体过大（上限 %d 字节）" % BODY_LIMIT})
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"error": "请求体不是合法 JSON"})
        with ctx.lock:
            try:
                result = execute_action(ctx, body)
            except yotta_kb.KbError as exc:
                return self._json(_kb_http_code(exc), {"error": exc.message, "code": exc.code})
            except Exception as exc:  # noqa: BLE001
                return self._json(500, {"error": str(exc)})
        return self._json(200, result)


# ── 启动 ────────────────────────────────────────────────────────────────────

def load_html():
    path = _HERE.parent / "assets" / "view.html"
    if not path.is_file():
        raise yotta_kb.KbIntegrityError("面板资源缺失：%s" % path)
    return path.read_text(encoding="utf-8")


def render_html(source, token):
    html = str(source or "")
    if TOKEN_PLACEHOLDER in html:
        return html.replace(TOKEN_PLACEHOLDER, token)
    meta = '<meta name="yotta-view-token" content="%s">' % token
    if "</head>" in html:
        return html.replace("</head>", meta + "</head>")
    return meta + html


def create_view_server(root_dir=None, port=DEFAULT_PORT, token=None):
    """创建（未启动）本地面板服务器；返回 (server, token, url)。"""
    requested = token or secrets.token_urlsafe(24)
    safe_token = requested if token_format_ok(requested) else secrets.token_urlsafe(24)
    html = render_html(load_html(), safe_token)
    ctx = ViewContext(explicit_dir=root_dir, token=safe_token, html=html)
    # fail-closed：启动前确认当前位置是可用知识库
    ctx.root()
    server = ThreadingHTTPServer((DEFAULT_HOST, int(port)), ViewHandler)
    server.daemon_threads = True
    server.view_ctx = ctx  # type: ignore[attr-defined]
    actual_port = server.server_address[1]
    return server, safe_token, "http://%s:%d/" % (DEFAULT_HOST, actual_port)


def token_format_ok(value):
    return bool(re.match(r"^[A-Za-z0-9_-]{8,128}$", str(value or "")))


def serve(root_dir=None, port=DEFAULT_PORT):
    server, token, url = create_view_server(root_dir=root_dir, port=port)
    root, source = server.view_ctx.root()  # type: ignore[attr-defined]
    print("元习知识库管理台已启动：%s" % url, flush=True)
    print("  KB: %s（来源: %s）" % (root, source), flush=True)
    print("  安全: 仅本机 127.0.0.1 / 页面内嵌会话令牌 / 写操作需确认串", flush=True)
    print("  退出: Ctrl+C", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()
    return 0

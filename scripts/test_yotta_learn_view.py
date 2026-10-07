# -*- coding: utf-8 -*-
"""test_yotta_learn_view.py — 元习本地管理台（yotta-learn view）自测套件。

覆盖：安全壳（Host / Origin / Sec-Fetch-Site / timing-safe 令牌）/ 只读端点 /
写操作全链路（category.create → entry.add → review → deprecate / index.rebuild /
location.set）/ 确认串 / 请求体上限 / 错误映射 / 审计 / 迁移后会话内切换 /
legacy 回退写拦截（409）。

运行：python scripts/test_yotta_learn_view.py
说明：测试进程把 HOME/USERPROFILE 指到临时目录，不触碰真实用户配置。
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import yotta_kb  # noqa: E402
import yotta_learn_view as v  # noqa: E402

PASS = 0
FAIL = 0
FAILED = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok  %s" % name)
    else:
        FAIL += 1
        FAILED.append(name)
        print("  FAIL %s  %s" % (name, detail))


def setup_kb(tmp):
    root = Path(tmp) / "kb"
    yotta_kb.init_kb(root, "tester@host")
    yotta_kb.create_category(root, "agent-skills", "智能体与技能开发",
                             "技能开发与编排相关知识", [], "tester@host")
    return root


def http(method, url, payload=None, headers=None, raw=None):
    data = raw if raw is not None else (
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if payload is not None else None)
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace"), dict(exc.headers or {})


class Server:
    def __init__(self, root):
        self.server, self.token, self.url = v.create_view_server(
            root_dir=str(root) if root is not None else None, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def test_security_helpers():
    check("host_allowed 127.0.0.1:8791", v.host_allowed("127.0.0.1:8791", 8791))
    check("host_allowed localhost", v.host_allowed("localhost", 8791))
    check("host_allowed 拒绝外部域", not v.host_allowed("evil.example:8791", 8791))
    check("host_allowed 拒绝错端口", not v.host_allowed("127.0.0.1:9999", 8791))
    check("origin_allowed 同源",
          v.origin_allowed("http://127.0.0.1:8791", "127.0.0.1:8791"))
    check("origin_allowed 拒绝跨域",
          not v.origin_allowed("http://evil.example", "127.0.0.1:8791"))
    check("fetch_site 允许 same-origin/none/缺省",
          v.fetch_site_allowed("same-origin") and v.fetch_site_allowed("none")
          and v.fetch_site_allowed(""))
    check("fetch_site 拒绝 cross-site", not v.fetch_site_allowed("cross-site"))
    check("token timing-safe 相等", v.token_allowed("abc12345", "abc12345"))
    check("token 拒绝不等", not v.token_allowed("abc12345", "abc12346"))
    check("token 格式白名单", v.token_format_ok("A" * 24)
          and not v.token_format_ok("短 token"))


def test_http_flow(tmp):
    root = setup_kb(tmp)
    srv = Server(root)
    base = srv.url.rstrip("/")
    auth = {v.TOKEN_HEADER: srv.token}
    try:
        code, body, headers = http("GET", base + "/")
        check("GET / 200 + 页面标题", code == 200 and "元习知识库" in body, str(code))
        check("GET / 含严格 CSP", "Content-Security-Policy" in headers, str(headers))
        check("GET / 页面内嵌会话令牌", srv.token in body)

        code, _body, _h = http("GET", base + "/api/overview",
                               headers={"Host": "evil.example"})
        check("Host 校验 403", code == 403, str(code))
        code, _body, _h = http("GET", base + "/api/overview",
                               headers={"Origin": "http://evil.example"})
        check("Origin 校验 403", code == 403, str(code))
        code, _body, _h = http("GET", base + "/api/overview",
                               headers={"Sec-Fetch-Site": "cross-site"})
        check("Sec-Fetch-Site 校验 403", code == 403, str(code))

        code, body, _h = http("GET", base + "/api/overview")
        data = json.loads(body)
        check("只读端点无需令牌",
              code == 200 and data["stats"]["categories"] == 1, body[:200])
        code, _body, _h = http("GET", base + "/api/location")
        check("location 端点 200", code == 200, str(code))

        code, _body, _h = http("POST", base + "/api/action",
                               payload={"action": "entry.add"})
        check("写操作无令牌 403", code == 403, str(code))
        code, _body, _h = http("POST", base + "/api/action",
                               payload={"action": "entry.add"},
                               headers={v.TOKEN_HEADER: "wrong-token-12345"})
        check("写操作错令牌 403", code == 403, str(code))

        code, body, _h = http("POST", base + "/api/action", headers=auth, payload={
            "action": "category.create", "slug": "release-ops",
            "name": "发布与运维", "description": "发布流程与运维知识"})
        check("category.create 200",
              code == 200 and json.loads(body)["slug"] == "release-ops", body[:200])

        code, body, _h = http("POST", base + "/api/action", headers=auth, payload={
            "action": "entry.add", "category": "agent-skills",
            "title": "面板写入条目", "message": "面板写入的正文内容",
            "source": "view-test", "tags": ["view", "kb"]})
        data = json.loads(body)
        eid = data.get("id", "")
        check("entry.add 草稿", code == 200 and data.get("status") == "draft", body[:200])

        code, body, _h = http("POST", base + "/api/action", headers=auth, payload={
            "action": "entry.review", "id": eid, "decision": "pass"})
        check("review 缺证据 400", code == 400, body[:200])
        code, body, _h = http("POST", base + "/api/action", headers=auth, payload={
            "action": "entry.review", "id": eid, "decision": "pass",
            "evidence": "面板自测核验"})
        check("review pass 200",
              code == 200 and json.loads(body)["status"] == "verified", body[:200])

        code, body, _h = http(
            "GET", base + "/api/search?q=" + urllib.parse.quote("面板写入"))
        check("search 命中已核验条目",
              code == 200 and json.loads(body)["count"] >= 1, body[:200])

        code, body, _h = http("POST", base + "/api/action", headers=auth, payload={
            "action": "entry.deprecate", "id": eid})
        check("deprecate 缺确认串 400", code == 400, body[:200])
        code, body, _h = http("POST", base + "/api/action", headers=auth, payload={
            "action": "entry.deprecate", "id": eid,
            "confirm": v.CONFIRM["entry_deprecate"], "reason": "面板自测"})
        check("deprecate 200",
              code == 200 and json.loads(body)["status"] == "deprecated", body[:200])

        code, body, _h = http("POST", base + "/api/action", headers=auth,
                              payload={"action": "nope"})
        check("未知操作 400", code == 400, body[:200])

        big = json.dumps({"action": "entry.add", "message": "x" * 70000})
        code, _body, _h = http("POST", base + "/api/action",
                               raw=big.encode("utf-8"), headers=auth)
        check("超大请求体 413", code == 413, str(code))

        code, _body, _h = http("GET", base + "/api/entry?id=KB-20200101-999")
        check("条目不存在 404", code == 404, str(code))

        audit_lines = (root / "audit" / "audit.jsonl").read_text(
            encoding="utf-8").splitlines()
        records = [json.loads(line) for line in audit_lines if line.strip()]
        check("审计含 view.entry.add",
              any(r.get("action") == "view.entry.add" for r in records), str(records[-3:]))

        target = Path(tmp) / "kb-new"
        code, body, _h = http("POST", base + "/api/action", headers=auth, payload={
            "action": "location.set", "dir": str(target), "move": True,
            "confirm": v.CONFIRM["location_move"]})
        data = json.loads(body)
        check("location.set move 200",
              code == 200 and Path(data.get("target", "")) == target.resolve(), body[:240])
        moved_ok = bool(data.get("movedTo")) and \
            (Path(data["movedTo"]) / "kb.json").exists()
        listing = sorted(os.listdir(tmp))
        root_listing = sorted(os.listdir(root)) if root.exists() else []
        check("迁移后旧库已移出",
              (not root.exists()) and moved_ok,
              "root_exists=%s moved_ok=%s tmp=%s root=%s body=%s"
              % (root.exists(), moved_ok, listing, root_listing, body))
        code, body, _h = http("GET", base + "/api/overview")
        check("迁移后会话指向新库",
              json.loads(body)["root"] == str(target.resolve()), body[:200])

        code, body, _h = http("POST", base + "/api/action", headers=auth, payload={
            "action": "location.set", "dir": str(Path(tmp) / "not-initialized"),
            "move": False, "confirm": v.CONFIRM["location_set"]})
        check("仅切换到未初始化目录被拒", code == 409, body[:200])
    finally:
        srv.close()


def test_legacy_write_block(tmp):
    home = Path(tmp) / "legacy-home"
    home.mkdir()
    old_default = home / ".yottaskills" / "knowledge"
    saved = {k: os.environ.get(k)
             for k in ("HOME", "USERPROFILE", "YOTTA_LEARN_KB")}
    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)
    os.environ["YOTTA_LEARN_KB"] = str(old_default)  # 建库阶段显式指定，避免初始拦截
    try:
        yotta_kb.init_kb(old_default, "tester@host")
        yotta_kb.create_category(old_default, "agent-skills", "智能体与技能开发",
                                 "技能开发与编排相关知识", [], "tester@host")
    finally:
        os.environ.pop("YOTTA_LEARN_KB", None)
    srv = Server(None)
    base = srv.url.rstrip("/")
    auth = {v.TOKEN_HEADER: srv.token}
    try:
        code, body, _h = http("GET", base + "/api/overview")
        check("legacy 回退时只读端点 200", code == 200, "%s %s" % (code, body[:200]))
        code, body, _h = http("POST", base + "/api/action", headers=auth, payload={
            "action": "entry.add", "category": "agent-skills",
            "title": "legacy 面板探针", "message": "正文", "source": "view-test"})
        check("legacy 回退时 entry.add 409 + 迁移指引",
              code == 409 and "旧版" in body and "--move" in body,
              "%s %s" % (code, body[:200]))
        code, body, _h = http("POST", base + "/api/action", headers=auth, payload={
            "action": "index.rebuild", "confirm": v.CONFIRM["index_rebuild"]})
        check("legacy 回退时 index.rebuild 409",
              code == 409, "%s %s" % (code, body[:200]))
    finally:
        srv.close()
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def main():
    tmp = tempfile.mkdtemp(prefix="yottalearn-view-test-")
    home = Path(tmp) / "home"
    home.mkdir()
    os.environ["USERPROFILE"] = str(home)
    os.environ["HOME"] = str(home)
    try:
        test_security_helpers()
        test_http_flow(tmp)
        test_legacy_write_block(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n结果：%d 通过 / %d 失败" % (PASS, FAIL))
    if FAILED:
        print("失败项：%s" % ", ".join(FAILED))
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()

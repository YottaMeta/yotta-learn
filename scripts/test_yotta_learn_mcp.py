# -*- coding: utf-8 -*-
"""test_yotta_learn_mcp.py — 元习知识库 MCP server（yotta-learn MCP）自测套件。

覆盖：initialize / tools.list（12 工具）/ 读写工具全链路（kb_add → kb_review →
kb_query / kb_get / kb_list / kb_stats / kb_categories）/ 写门禁（缺证据 / 敏感
阻断 + force / 更新 / 停用）/ 运维（doctor / index rebuild）/ 错误路径 / modern
（2026-07-28 server/discover）/ stdio 端到端。

运行：python scripts/test_yotta_learn_mcp.py
说明：敏感示例字符串用拼接构造，避免作为字面量进入发布包被扫描命中。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import yotta_learn_mcp as m  # noqa: E402
import yotta_kb  # noqa: E402

PASS = 0
FAIL = 0
FAILED = []

MODERN_META = {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok  %s" % name)
    else:
        FAIL += 1
        FAILED.append(name)
        print("  FAIL %s  %s" % (name, detail))


def call(name, arguments):
    return m.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                             "params": {"name": name, "arguments": arguments}})


def payload(resp):
    return json.loads(resp["result"]["content"][0]["text"])


def setup_kb(tmp):
    root = Path(tmp) / "kb"
    yotta_kb.init_kb(root, "tester@host")
    yotta_kb.create_category(root, "agent-skills", "智能体与技能开发",
                             "技能开发与编排相关知识", [], "tester@host")
    return root


def test_initialize():
    resp = m.handle_message({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                   "clientInfo": {"name": "t", "version": "1"}}})
    check("initialize 返回 legacy protocolVersion 2025-11-25",
          resp.get("result", {}).get("protocolVersion") == "2025-11-25", str(resp))
    check("initialize serverInfo.name = yotta-learn",
          resp.get("result", {}).get("serverInfo", {}).get("name") == "yotta-learn", str(resp))
    check("initialize version = 0.4.0",
          resp.get("result", {}).get("serverInfo", {}).get("version") == "0.4.0", str(resp))
    check("initialize capabilities.tools 存在",
          "tools" in resp.get("result", {}).get("capabilities", {}), str(resp))


def test_tools_list():
    resp = m.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = resp.get("result", {}).get("tools", [])
    names = {t["name"] for t in tools}
    expected = {"kb_query", "kb_get", "kb_list", "kb_stats", "kb_categories",
                "kb_add", "kb_review", "kb_update", "kb_deprecate",
                "kb_category_create", "kb_doctor", "kb_index_rebuild"}
    check("tools/list 含 12 个工具", len(tools) == 12, str(names))
    check("tools/list 名称集合正确", names == expected, str(names))
    for t in tools:
        check("工具 %s 有 inputSchema.properties" % t["name"],
              isinstance(t.get("inputSchema", {}).get("properties"), dict), str(t))


def test_read_write_flow(tmp):
    root = setup_kb(Path(tmp) / "flow")
    resp = call("kb_categories", {"dir": str(root)})
    data = payload(resp)
    check("kb_categories 返回 1 个分类",
          resp["result"]["isError"] is False and data["count"] == 1, str(data))

    resp = call("kb_add", {
        "dir": str(root), "category": "agent-skills", "title": "MCP 写入条目",
        "message": "通过 MCP 写入的正文内容", "source": "test",
        "tags": ["mcp", "kb"], "evidence": "本机实测", "agent": "tester"})
    data = payload(resp)
    check("kb_add 成功且为草稿",
          resp["result"]["isError"] is False and data["status"] == "draft", str(data))
    eid = data["id"]

    resp = call("kb_review", {"dir": str(root), "id": eid, "decision": "pass",
                              "evidence": "MCP 自测核验", "agent": "tester"})
    data = payload(resp)
    check("kb_review pass 后 verified",
          resp["result"]["isError"] is False and data["status"] == "verified", str(data))

    resp = call("kb_query", {"dir": str(root), "keywords": "MCP 写入"})
    data = payload(resp)
    check("kb_query 命中已核验条目",
          resp["result"]["isError"] is False and data["count"] >= 1
          and any(r["id"] == eid for r in data["results"]), str(data))

    resp = call("kb_get", {"dir": str(root), "id": eid})
    data = payload(resp)
    check("kb_get 返回正文",
          data.get("id") == eid and "通过 MCP 写入的正文内容" in data.get("body", ""), str(data))

    resp = call("kb_list", {"dir": str(root), "category": "agent-skills"})
    data = payload(resp)
    check("kb_list 返回条目", data["count"] >= 1, str(data))

    resp = call("kb_stats", {"dir": str(root)})
    data = payload(resp)
    check("kb_stats total >= 1", data["total"] >= 1, str(data))


def test_write_gates(tmp):
    root = setup_kb(Path(tmp) / "gates")
    resp = call("kb_add", {"dir": str(root), "category": "agent-skills",
                           "title": "缺正文"})
    check("kb_add 缺 message 报错", resp["result"]["isError"] is True, str(resp))

    resp = call("kb_add", {"dir": str(root), "category": "agent-skills",
                           "title": "门禁草稿", "message": "草稿正文",
                           "source": "test"})
    eid = payload(resp)["id"]
    resp = call("kb_query", {"dir": str(root), "keywords": "门禁草稿"})
    check("默认查询不含草稿", payload(resp)["count"] == 0, str(resp))

    resp = call("kb_review", {"dir": str(root), "id": eid, "decision": "pass"})
    check("kb_review pass 缺证据被门禁阻断",
          resp["result"]["isError"] is True, str(resp))

    sensitive = "api" + "_key = " + "abcdefghijklmnop1234"
    resp = call("kb_add", {"dir": str(root), "category": "agent-skills",
                           "title": "敏感草稿", "message": sensitive,
                           "source": "test", "evidence": "x"})
    data = payload(resp)
    eid2 = data["id"]
    check("kb_add 返回敏感命中", len(data["sensitive"]) >= 1, str(data))
    resp = call("kb_review", {"dir": str(root), "id": eid2, "decision": "pass",
                              "evidence": "x"})
    check("敏感条目核验被阻断", resp["result"]["isError"] is True, str(resp))
    resp = call("kb_review", {"dir": str(root), "id": eid2, "decision": "pass",
                              "evidence": "x", "force": True, "note": "自测放行"})
    data = payload(resp)
    check("force=true 显式放行并返回命中",
          resp["result"]["isError"] is False and len(data["findings"]) >= 1, str(data))

    resp = call("kb_update", {"dir": str(root), "id": eid,
                              "title": "门禁草稿-改", "tags": ["updated"]})
    check("kb_update 成功", resp["result"]["isError"] is False, str(resp))
    resp = call("kb_get", {"dir": str(root), "id": eid})
    check("kb_update 生效", payload(resp)["title"] == "门禁草稿-改", str(resp))
    resp = call("kb_deprecate", {"dir": str(root), "id": eid, "reason": "自测"})
    check("kb_deprecate 停用成功",
          payload(resp)["status"] == "deprecated", str(resp))

    resp = call("kb_add", {"dir": str(root), "category": "agent-skills",
                           "title": "待拒绝条目", "message": "正文", "source": "test"})
    eid3 = payload(resp)["id"]
    resp = call("kb_review", {"dir": str(root), "id": eid3, "decision": "reject",
                              "note": "自测拒绝"})
    check("kb_review reject 成功",
          resp["result"]["isError"] is False and payload(resp)["decision"] == "reject",
          str(resp))


def test_ops(tmp):
    root = setup_kb(Path(tmp) / "ops")
    resp = call("kb_doctor", {"dir": str(root)})
    data = payload(resp)
    check("kb_doctor errors = 0",
          resp["result"]["isError"] is False and data["errors"] == 0, str(data))
    resp = call("kb_index_rebuild", {"dir": str(root), "agent": "tester"})
    data = payload(resp)
    check("kb_index_rebuild 返回统计",
          isinstance(data.get("total_entries"), int), str(data))


def test_errors(tmp):
    root = setup_kb(Path(tmp) / "errors")
    resp = call("nope", {})
    check("未知工具 isError", resp["result"]["isError"] is True, str(resp))
    resp = call("kb_get", {"dir": str(root), "id": "KB-20200101-999"})
    check("kb_get 不存在条目 isError", resp["result"]["isError"] is True, str(resp))
    resp = call("kb_stats", {"dir": str(Path(tmp) / "missing-kb")})
    check("未初始化库 isError", resp["result"]["isError"] is True, str(resp))
    resp = call("kb_category_create", {"dir": str(root), "slug": "Bad Slug",
                                       "name": "x", "description": "y"})
    check("非法分类 slug isError", resp["result"]["isError"] is True, str(resp))


def test_modern():
    resp = m.handle_message({"jsonrpc": "2.0", "id": 10, "method": "server/discover",
                             "params": dict(MODERN_META)})
    result = resp.get("result", {})
    check("modern server/discover resultType complete",
          result.get("resultType") == "complete"
          and "2026-07-28" in result.get("supportedVersions", []), str(resp))
    resp = m.handle_message({"jsonrpc": "2.0", "id": 11, "method": "tools/list",
                             "params": dict(MODERN_META)})
    check("modern tools/list 12 工具",
          resp.get("result", {}).get("resultType") == "complete"
          and len(resp["result"]["tools"]) == 12, str(resp)[:200])
    resp = m.handle_message({"jsonrpc": "2.0", "id": 12, "method": "tools/call",
                             "params": {"_meta": MODERN_META["_meta"], "name": "nope",
                                        "arguments": {}}})
    check("modern tools/call 未知工具 isError",
          resp["result"].get("isError") is True, str(resp)[:200])
    resp = m.handle_message({"jsonrpc": "2.0", "id": 13, "method": "tools/list",
                             "params": {"_meta": {
                                 "io.modelcontextprotocol/protocolVersion": "2025-11-25"}}})
    check("modern 不支持版本返回 -32022",
          resp.get("error", {}).get("code") == -32022, str(resp))
    resp = m.handle_message({"jsonrpc": "2.0", "id": 14, "method": "initialize",
                             "params": dict(MODERN_META)})
    check("modern initialize 拒绝 -32601",
          resp.get("error", {}).get("code") == -32601, str(resp))
    resp = m.handle_message({"jsonrpc": "2.0", "id": 15, "method": "bad/method",
                             "params": dict(MODERN_META)})
    check("modern 未知 method -32601",
          resp.get("error", {}).get("code") == -32601, str(resp))
    check("通知（无 id）不响应",
          m.handle_message({"jsonrpc": "2.0", "method": "ping"}) is None)


def test_stdio_subprocess(tmp):
    root = setup_kb(Path(tmp) / "stdio")
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                    "clientInfo": {"name": "t", "version": "1"}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "kb_stats", "arguments": {"dir": str(root)}}},
    ]
    input_text = "\n".join(json.dumps(x) for x in lines) + "\n"
    script = str(_HERE / "yotta_learn_mcp.py")
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run([sys.executable, script], input=input_text,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(_HERE), env=env, timeout=60)
    out = [ln for ln in r.stdout.splitlines() if ln.strip()]
    check("stdio 端到端产出 2 行", len(out) == 2, "%d 行: %s" % (len(out), r.stdout[:200]))
    if len(out) >= 2:
        first = json.loads(out[0])
        check("stdio initialize id=1",
              first.get("id") == 1
              and first.get("result", {}).get("serverInfo", {}).get("name") == "yotta-learn",
              out[0][:120])
        second = json.loads(out[1])
        check("stdio kb_stats 非 error",
              second.get("result", {}).get("isError") is False, out[1][:160])


def main():
    tmp = tempfile.mkdtemp(prefix="yottalearn-mcp-test-")
    try:
        test_initialize()
        test_tools_list()
        test_read_write_flow(tmp)
        test_write_gates(tmp)
        test_ops(tmp)
        test_errors(tmp)
        test_modern()
        test_stdio_subprocess(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n结果：%d 通过 / %d 失败" % (PASS, FAIL))
    if FAILED:
        print("失败项：%s" % ", ".join(FAILED))
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""yotta-learn 知识库（KB v1）测试套件。

用法：
  python3 scripts/test_yotta_kb.py
覆盖：frontmatter 协议（往返 / fail-closed / 注释与转义）、切词、init 防覆盖、
位置配置（set/get/clear + env 覆盖）、分类（创建 / 查重 / 合并 / 停用）、
条目（add / update / review / reject / deprecate / 去重）、查询（中文 bigram /
过滤 / 评分 / 空结果 / 降级线性扫描）、可靠性（锁 / 回收站 / 快照 / 备份 /
doctor / 索引漂移）与退出码。
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "yotta_learn.py"
sys.path.insert(0, str(HERE))
import yotta_kb  # noqa: E402
import yotta_kb_index  # noqa: E402


class KbUnitTest(unittest.TestCase):
    """协议与切词的直接单元测试（不起子进程）。"""

    def test_frontmatter_roundtrip(self):
        fields = yotta_kb.new_entry_fields(
            "KB-20261005-001", "It's a: test 中文", "agent-skills",
            ["a", "中文"], "https://example.com/x?a=1", "证据",
            "high", "codex@host")
        body = "## 要点\n\n内容 line1\nline2"
        text = yotta_kb.dump_entry_text(fields, body)
        parsed, parsed_body = yotta_kb.parse_entry_text(text)
        self.assertEqual(parsed, fields)
        self.assertEqual(parsed_body, body)

    def test_frontmatter_fail_closed(self):
        with self.assertRaises(yotta_kb.KbIntegrityError):
            yotta_kb.parse_entry_text("---\nfoo: bar\n---\n")
        with self.assertRaises(yotta_kb.KbIntegrityError):
            yotta_kb.parse_entry_text("---\nid: x\n")
        with self.assertRaises(yotta_kb.KbIntegrityError):
            yotta_kb.parse_entry_text("---\ntags: not-array\n---\n")
        with self.assertRaises(yotta_kb.KbUsageError):
            yotta_kb.dump_entry_text({"id": "KB-20261005-001", "title": "a\nb"}, "")

    def test_scalar_comments_and_quotes(self):
        fields, _ = yotta_kb.parse_entry_text(
            "---\nid: KB-20261005-001\ntitle: 'It''s fine'\n"
            "status: draft # 注释\ncategory: agent-skills\n"
            "tags: [\"a\", \"b\"]\n---\n")
        self.assertEqual(fields["title"], "It's fine")
        self.assertEqual(fields["status"], "draft")
        self.assertEqual(fields["tags"], ["a", "b"])

    def test_tokenize(self):
        toks = yotta_kb_index.tokenize_query("中文检索")
        self.assertIn("中文", toks)
        self.assertIn("检索", toks)
        self.assertEqual(yotta_kb_index.tokenize_query("坑"), ["坑"])
        self.assertIn("sqlite", yotta_kb_index.tokenize_query("SQLite FTS5"))
        doc = yotta_kb_index.tokenize_document("中文检索")
        self.assertIn("检索", doc)
        self.assertIn("中", doc)


class KbCliTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.dir = Path(self.td.name)
        self.home = self.dir / "home"
        self.home.mkdir()
        self.kb = self.dir / "kb"

    def tearDown(self):
        self.td.cleanup()

    def run_cli(self, args, extra_env=None, timeout=90):
        env = dict(os.environ)
        env["YOTTA_LEARN_AGENT"] = "tester"
        env["USERPROFILE"] = str(self.home)
        env["HOME"] = str(self.home)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(SCRIPT)] + args,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(self.dir), env=env, timeout=timeout,
        )

    def kb_args(self, *args):
        return list(args) + ["--dir", str(self.kb)]

    def init_kb(self):
        r = self.run_cli(self.kb_args("kb", "init"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def make_category(self, slug="agent-skills", name="智能体与技能开发",
                      description="技能开发与编排相关知识与方法"):
        r = self.run_cli(self.kb_args(
            "kb", "category", "create", slug,
            "--name", name, "--description", description))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def add_entry(self, title, message="正文内容", category="agent-skills",
                  source="experiment", tags=None, evidence=None):
        args = self.kb_args("kb", "add", "--category", category, "--title", title,
                            "--message", message, "--source", source, "--json")
        if tags:
            args += ["--tags", ",".join(tags)]
        if evidence:
            args += ["--evidence", evidence]
        r = self.run_cli(args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)["id"]

    def verify_entry(self, eid, evidence="本地实测通过"):
        r = self.run_cli(self.kb_args(
            "kb", "review", eid, "--pass", "--evidence", evidence))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def query_json(self, *keywords, extra=None):
        args = self.kb_args("kb", "query") + list(keywords) + ["--json"]
        if extra:
            args += extra
        r = self.run_cli(args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    # ── init / config ──────────────────────────────────────────────────────

    def test_init_fail_closed(self):
        self.init_kb()
        self.assertTrue((self.kb / "kb.json").exists())
        self.assertTrue((self.kb / "index" / "global.json").exists())
        r = self.run_cli(self.kb_args("kb", "init"))
        self.assertEqual(r.returncode, 6, r.stdout + r.stderr)
        other = self.dir / "not-empty"
        other.mkdir()
        (other / "x.txt").write_text("x", encoding="utf-8")
        r2 = self.run_cli(["kb", "init", "--dir", str(other)])
        self.assertEqual(r2.returncode, 6, r2.stdout + r2.stderr)

    def test_config_set_get_clear_and_env(self):
        r = self.run_cli(["kb", "config", "set", "--dir", str(self.kb)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r2 = self.run_cli(["kb", "config", "get"])
        self.assertEqual(r2.returncode, 0, r2.stdout + r.stderr)
        self.assertIn(str(self.kb), r2.stdout)
        self.assertIn("配置文件", r2.stdout)
        env_root = self.dir / "env-kb"
        r3 = self.run_cli(["kb", "config", "get"],
                          extra_env={"YOTTA_LEARN_KB": str(env_root)})
        self.assertIn(str(env_root), r3.stdout)
        self.assertIn("YOTTA_LEARN_KB", r3.stdout)
        r4 = self.run_cli(["kb", "config", "clear"])
        self.assertEqual(r4.returncode, 0, r4.stdout + r4.stderr)
        self.assertFalse((self.home / ".yottaskills" / "yotta-learn.json").exists())

    # ── 分类 ───────────────────────────────────────────────────────────────

    def test_category_create_validation_and_list(self):
        self.init_kb()
        self.make_category()
        r = self.run_cli(self.kb_args(
            "kb", "category", "create", "agent-skills",
            "--name", "重复", "--description", "重复分类"))
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        r2 = self.run_cli(self.kb_args(
            "kb", "category", "create", "Bad Slug",
            "--name", "非法", "--description", "非法 slug"))
        self.assertEqual(r2.returncode, 4, r2.stdout + r2.stderr)
        r3 = self.run_cli(self.kb_args("kb", "category", "list", "--json"))
        data = json.loads(r3.stdout)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["slug"], "agent-skills")
        self.assertEqual(data[0]["status"], "active")

    def test_category_merge_alias_and_snapshot(self):
        self.init_kb()
        self.make_category("release-ops", "发布与运维", "发布流程与运维知识")
        self.make_category("agent-skills")
        eid = self.add_entry("合并前条目", category="agent-skills")
        r = self.run_cli(self.kb_args(
            "kb", "category", "merge", "agent-skills", "--into", "release-ops"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("迁移 1 条", r.stdout)
        # 旧 slug 变为别名：写入自动落到目标分类
        eid2 = self.add_entry("别名写入条目", category="agent-skills")
        r2 = self.run_cli(self.kb_args("kb", "show", eid2, "--json"))
        self.assertEqual(json.loads(r2.stdout)["category"], "release-ops")
        r3 = self.run_cli(self.kb_args("kb", "show", eid, "--json"))
        self.assertEqual(json.loads(r3.stdout)["category"], "release-ops")
        # 快照 + 审计
        snaps = json.loads(self.run_cli(self.kb_args(
            "kb", "snapshot", "list", "--json")).stdout)
        self.assertTrue(any("merge" in s["op"] for s in snaps))
        audit = (self.kb / "audit" / "audit.jsonl").read_text(encoding="utf-8")
        self.assertIn("kb.category.merge", audit)

    def test_category_deprecate_rules(self):
        self.init_kb()
        self.make_category()
        self.add_entry("占用分类的条目")
        r = self.run_cli(self.kb_args("kb", "category", "deprecate", "agent-skills"))
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        r2 = self.run_cli(self.kb_args(
            "kb", "category", "deprecate", "agent-skills", "--force"))
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        r3 = self.run_cli(self.kb_args(
            "kb", "add", "--category", "agent-skills", "--title", "x",
            "--message", "y", "--source", "z"))
        self.assertEqual(r3.returncode, 4, r3.stdout + r3.stderr)

    # ── 条目与审核 ─────────────────────────────────────────────────────────

    def test_add_validation_and_ids(self):
        self.init_kb()
        self.make_category()
        r = self.run_cli(self.kb_args(
            "kb", "add", "--category", "agent-skills", "--title", "无出处",
            "--message", "x"))
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        r2 = self.run_cli(self.kb_args(
            "kb", "add", "--category", "nope", "--title", "x",
            "--message", "y", "--source", "z"))
        self.assertEqual(r2.returncode, 4, r2.stdout + r2.stderr)
        eid1 = self.add_entry("第一条")
        eid2 = self.add_entry("第二条")
        self.assertNotEqual(eid1, eid2)
        self.assertTrue(eid1.startswith("KB-"))
        self.assertTrue(eid2.endswith("002"))

    def test_sensitive_scan_blocks_review(self):
        self.init_kb()
        self.make_category()
        eid = self.add_entry(
            "含密钥样例", message="api_key = sk-abcdefghijklmnopqrstuvwxyz123456")
        r = self.run_cli(self.kb_args("kb", "review", eid, "--pass",
                                      "--evidence", "本地验证"))
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        r2 = self.run_cli(self.kb_args(
            "kb", "review", eid, "--pass", "--evidence", "已脱敏确认",
            "--force", "--note", "样例已脱敏"))
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)

    def test_review_checklist_and_evidence_required(self):
        self.init_kb()
        self.make_category()
        eid = self.add_entry("待核验条目")
        r = self.run_cli(self.kb_args("kb", "review", eid))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("质检三问", r.stdout)
        r2 = self.run_cli(self.kb_args("kb", "review", eid, "--pass"))
        self.assertEqual(r2.returncode, 4, r2.stdout + r2.stderr)
        self.verify_entry(eid)
        r3 = self.run_cli(self.kb_args("kb", "show", eid, "--json"))
        data = json.loads(r3.stdout)
        self.assertEqual(data["status"], "verified")
        self.assertTrue(data["verified_by"].startswith("tester@"))

    def test_review_reject_moves_to_trash(self):
        self.init_kb()
        self.make_category()
        eid = self.add_entry("将被拒绝")
        r = self.run_cli(self.kb_args("kb", "review", eid, "--reject",
                                      "--note", "信息不完整"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r2 = self.run_cli(self.kb_args("kb", "show", eid))
        self.assertEqual(r2.returncode, 1, r2.stdout + r2.stderr)
        trash = json.loads(self.run_cli(self.kb_args(
            "kb", "trash", "list", "--json")).stdout)
        self.assertEqual(len(trash), 1)
        audit = (self.kb / "audit" / "audit.jsonl").read_text(encoding="utf-8")
        self.assertIn("kb.review.reject", audit)

    def test_review_duplicate_blocks(self):
        self.init_kb()
        self.make_category()
        eid1 = self.add_entry("重复标题测试")
        self.verify_entry(eid1)
        eid2 = self.add_entry("重复标题测试")
        r = self.run_cli(self.kb_args("kb", "review", eid2, "--pass",
                                      "--evidence", "本地验证"))
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        r2 = self.run_cli(self.kb_args("kb", "review", eid2, "--pass",
                                       "--evidence", "本地验证", "--force"))
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)

    def test_update_and_deprecate_entry(self):
        self.init_kb()
        self.make_category()
        eid = self.add_entry("原始标题")
        r = self.run_cli(self.kb_args(
            "kb", "update", eid, "--title", "更新后的独特标题",
            "--tags", "新标签"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        result = self.query_json("独特标题", extra=["--include-draft"])
        self.assertEqual(result["results"][0]["id"], eid)
        r2 = self.run_cli(self.kb_args("kb", "update", eid))
        self.assertEqual(r2.returncode, 4, r2.stdout + r2.stderr)
        self.verify_entry(eid)
        r3 = self.run_cli(self.kb_args("kb", "deprecate", eid, "--reason", "已被替代"))
        self.assertEqual(r3.returncode, 0, r3.stdout + r3.stderr)
        self.assertEqual(self.query_json("更新后的独特标题")["count"], 0)
        found = self.query_json("更新后的独特标题", extra=["--status", "deprecated"])
        self.assertEqual(found["results"][0]["id"], eid)

    # ── 查询 ───────────────────────────────────────────────────────────────

    def test_query_bigram_scoring_and_filters(self):
        self.init_kb()
        self.make_category()
        title_hit = self.add_entry("独特关键词标题", message="普通内容")
        body_hit = self.add_entry("普通标题B", message="正文包含 独特关键词 内容")
        self.verify_entry(title_hit)
        self.verify_entry(body_hit)
        result = self.query_json("独特关键词")
        self.assertEqual(result["mode"], "index")
        self.assertEqual(result["results"][0]["id"], title_hit)
        latin = self.add_entry("FTS5 tokenizer notes", message="sqlite 分词")
        self.verify_entry(latin)
        result2 = self.query_json("fts5")
        self.assertEqual(result2["results"][0]["id"], latin)
        tagged = self.add_entry("标签过滤条目", tags=["检索", "中文"])
        self.verify_entry(tagged)
        result3 = self.query_json("标签过滤", extra=["--tag", "检索"])
        self.assertEqual(result3["count"], 1)
        result4 = self.query_json("标签过滤", extra=["--tag", "不存在"])
        self.assertEqual(result4["count"], 0)

    def test_query_status_gates_and_limit(self):
        self.init_kb()
        self.make_category()
        verified = self.add_entry("状态门条目")
        self.verify_entry(verified)
        draft = self.add_entry("状态门草稿")
        default = self.query_json("状态门")
        self.assertEqual(default["count"], 1)
        with_draft = self.query_json("状态门", extra=["--include-draft"])
        self.assertEqual(with_draft["count"], 2)
        only_draft = self.query_json("状态门", extra=["--status", "draft"])
        self.assertEqual(only_draft["results"][0]["id"], draft)
        for i in range(2):
            eid = self.add_entry("蓝鲸限量词%d" % i)
            self.verify_entry(eid)
        limited = self.query_json("蓝鲸限量词", extra=["--limit", "1"])
        self.assertEqual(limited["count"], 2)
        self.assertEqual(len(limited["results"]), 1)
        empty = self.query_json("绝不存在词组zzz")
        self.assertEqual(empty["count"], 0)

    # ── 索引 / doctor / 可靠性 ─────────────────────────────────────────────

    def test_index_drift_fallback_and_rebuild(self):
        self.init_kb()
        self.make_category()
        eid = self.add_entry("漂移测试条目", message="索引漂移验证")
        self.verify_entry(eid)
        entry_file = self.kb / "categories" / "agent-skills" / "entries" / (eid + ".md")
        with open(str(entry_file), "a", encoding="utf-8") as fh:
            fh.write("\n外部追加内容\n")
        r = self.run_cli(self.kb_args("kb", "index", "status"))
        self.assertIn("漂移", r.stdout)
        result = self.query_json("漂移测试")
        self.assertTrue(result["stale"])
        self.assertEqual(result["mode"], "linear")
        self.assertEqual(result["count"], 1)
        r2 = self.run_cli(self.kb_args("kb", "index", "rebuild"))
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        r3 = self.run_cli(self.kb_args("kb", "index", "status"))
        self.assertIn("健康", r3.stdout)

    def test_doctor_detects_corrupt_entry(self):
        self.init_kb()
        self.make_category()
        eid = self.add_entry("损坏前条目")
        r = self.run_cli(self.kb_args("kb", "doctor"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        entry_file = self.kb / "categories" / "agent-skills" / "entries" / (eid + ".md")
        entry_file.write_text("not a valid entry", encoding="utf-8")
        r2 = self.run_cli(self.kb_args("kb", "doctor"))
        self.assertEqual(r2.returncode, 1, r2.stdout + r2.stderr)
        self.assertIn("[error]", r2.stdout)

    def test_write_lock_timeout(self):
        self.init_kb()
        self.make_category()
        lock = self.kb / ".lock"
        lock.write_text("999999 2026-10-05T00:00:00+08:00\n", encoding="utf-8")
        r = self.run_cli(self.kb_args(
            "kb", "category", "create", "locked-cat",
            "--name", "锁测试", "--description", "锁测试分类"),
            extra_env={"YOTTA_LEARN_LOCK_TIMEOUT": "1"})
        self.assertEqual(r.returncode, 6, r.stdout + r.stderr)
        lock.unlink()

    def test_trash_purge(self):
        self.init_kb()
        self.make_category()
        eid = self.add_entry("过期回收条目")
        self.run_cli(self.kb_args("kb", "review", eid, "--reject", "--note", "过期"))
        trash_files = list((self.kb / ".trash").glob("*.md"))
        self.assertEqual(len(trash_files), 1)
        old = time.time() - 8 * 86400
        os.utime(str(trash_files[0]), (old, old))
        r = self.run_cli(self.kb_args("kb", "trash", "purge", "--days", "7"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("删除 1", r.stdout)
        self.assertEqual(len(list((self.kb / ".trash").glob("*.md"))), 0)

    def test_snapshot_restore(self):
        self.init_kb()
        self.make_category()
        eid = self.add_entry("快照恢复条目")
        self.verify_entry(eid)
        self.run_cli(self.kb_args("kb", "deprecate", eid, "--reason", "临时停用"))
        snaps = json.loads(self.run_cli(self.kb_args(
            "kb", "snapshot", "list", "--json")).stdout)
        target = [s for s in snaps if "deprecate" in s["op"]][0]
        r = self.run_cli(self.kb_args("kb", "snapshot", "restore", target["name"]))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        result = self.query_json("快照恢复")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["status"], "verified")

    def test_backup_create_list_restore(self):
        self.init_kb()
        self.make_category()
        eid = self.add_entry("备份恢复条目")
        self.verify_entry(eid)
        out = self.dir / "backups"
        r = self.run_cli(self.kb_args("kb", "backup", "create", "--out", str(out)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        items = json.loads(self.run_cli(
            ["kb", "backup", "list", "--out", str(out), "--json"]).stdout)
        self.assertEqual(len(items), 1)
        name = items[0]["name"]
        into = self.dir / "restored"
        r2 = self.run_cli(["kb", "backup", "restore", name,
                           "--out", str(out), "--into", str(into)])
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        result = json.loads(self.run_cli(
            ["kb", "query", "备份恢复", "--dir", str(into), "--json"]).stdout)
        self.assertEqual(result["count"], 1)
        (into / "extra.txt").write_text("x", encoding="utf-8")
        r3 = self.run_cli(["kb", "backup", "restore", name,
                           "--out", str(out), "--into", str(into)])
        self.assertEqual(r3.returncode, 6, r3.stdout + r3.stderr)
        r4 = self.run_cli(["kb", "backup", "restore", name,
                           "--out", str(out), "--into", str(into), "--force"])
        self.assertEqual(r4.returncode, 0, r4.stdout + r4.stderr)

    # ── 身份与退出码 ───────────────────────────────────────────────────────

    def test_agent_identity_flag_and_audit(self):
        self.init_kb()
        self.make_category()
        r = self.run_cli(self.kb_args(
            "kb", "add", "--category", "agent-skills", "--title", "身份条目",
            "--message", "x", "--source", "y", "--agent", "mybot", "--json"))
        eid = json.loads(r.stdout)["id"]
        shown = json.loads(self.run_cli(self.kb_args(
            "kb", "show", eid, "--json")).stdout)
        self.assertTrue(shown["author"].startswith("mybot@"))
        audit_lines = (self.kb / "audit" / "audit.jsonl").read_text(
            encoding="utf-8").splitlines()
        records = [json.loads(line) for line in audit_lines if line.strip()]
        add_records = [rec for rec in records if rec["action"] == "kb.add"]
        self.assertTrue(add_records[0]["actor"].startswith("mybot@"))

    def test_exit_codes(self):
        self.init_kb()
        r = self.run_cli(self.kb_args("kb", "show", "KB-20200101-999"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        r2 = self.run_cli(self.kb_args("kb", "nonsense"))
        self.assertEqual(r2.returncode, 4, r2.stdout + r2.stderr)
        r3 = self.run_cli(self.kb_args("kb", "query"))
        self.assertEqual(r3.returncode, 4, r3.stdout + r3.stderr)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    ok = unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
    sys.exit(0 if ok else 1)

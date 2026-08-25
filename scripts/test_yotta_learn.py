# -*- coding: utf-8 -*-
"""yotta-learn（元习）测试套件。

用法：
  python3 scripts/test_yotta_learn.py
覆盖：init/log/list/promote/review/stats/extract 全命令、去重、复发模式、
yotta-memory 联动四态（A 未装 / B 不可用 / C 超时 / ok 同步）、GBK 控制台加固。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "yotta_learn.py"


def run_cli(args, cwd, env=None):
    full = dict(os.environ)
    if env:
        full.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(cwd), env=full, timeout=60,
    )


def make_fake_ym(bin_dir, mode):
    """生成假的 yotta-memory 命令（mode: ok / fail / timeout）。"""
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim_py = bin_dir / "fake_ym.py"
    if mode == "ok":
        body = '''import sys
args = sys.argv[1:]
if args and args[0] == "whoami":
    print("agent: codex"); sys.exit(0)
if args and args[0] == "search":
    print("no results"); sys.exit(0)
if args and args[0] == "remember":
    print("remembered"); sys.exit(0)
sys.exit(0)
'''
    elif mode == "fail":
        body = '''import sys
if len(sys.argv) > 1 and sys.argv[1] == "whoami":
    sys.stderr.write("not initialized\\n"); sys.exit(1)
sys.exit(1)
'''
    else:  # timeout
        body = '''import time
time.sleep(30)
'''
    (bin_dir / "fake_ym.py").write_text(body, encoding="utf-8")
    cmd = bin_dir / "yotta-memory.cmd"
    cmd.write_text('@echo off\r\npython "%s\\fake_ym.py" %%*\r\n' % str(bin_dir), encoding="utf-8")


class LearnCliTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.dir = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_init_idempotent(self):
        r1 = run_cli(["init"], self.dir)
        self.assertEqual(r1.returncode, 0, r1.stderr)
        r2 = run_cli(["init"], self.dir)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertTrue((self.dir / ".learnings" / "LEARNINGS.md").exists())

    def test_log_list_all_types(self):
        run_cli(["log", "--type", "learning", "--message", "learn A"], self.dir)
        run_cli(["log", "--type", "error", "--message", "error B"], self.dir)
        run_cli(["log", "--type", "feature", "--message", "feature C"], self.dir)
        r = run_cli(["list", "--json"], self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual(len(data), 3)
        kinds = {e["type"] for e in data}
        self.assertEqual(kinds, {"learning", "error", "feature"})

    def test_log_requires_message(self):
        r = run_cli(["log"], self.dir)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)

    def test_bad_command_exit4(self):
        r = run_cli(["nonsense"], self.dir)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)

    def test_list_filters(self):
        run_cli(["log", "--type", "learning", "--category", "correction",
                 "--priority", "high", "--status", "pending", "--area", "git",
                 "--message", "filter me"], self.dir)
        run_cli(["log", "--type", "learning", "--category", "insight",
                 "--message", "other"], self.dir)
        r = run_cli(["list", "--category", "correction", "--json"], self.dir)
        data = json.loads(r.stdout)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["category"], "correction")
        self.assertEqual(data[0]["area"], "git")

    def test_promote_and_dedup(self):
        r1 = run_cli(["log", "--message", "promote me"], self.dir)
        eid = r1.stdout.split()[1]
        r2 = run_cli(["promote", eid], self.dir)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertTrue((self.dir / ".learnings" / "AGENTS.md").exists())
        # 再提升一次 → 自动去重
        r3 = run_cli(["promote", eid], self.dir)
        self.assertIn("去重", r3.stdout)

    def test_review(self):
        run_cli(["log", "--message", "pending item"], self.dir)
        r = run_cli(["review"], self.dir)
        self.assertIn("pending item", r.stdout)

    def test_stats(self):
        run_cli(["log", "--message", "stat item"], self.dir)
        r = run_cli(["stats"], self.dir)
        self.assertIn("总条目", r.stdout)

    def test_extract(self):
        r1 = run_cli(["log", "--area", "testing", "--message", "extract me"], self.dir)
        eid = r1.stdout.split()[1]
        r2 = run_cli(["extract", eid, "--slug", "test-skill"], self.dir)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        out = self.dir / ".learnings" / "extracted-skills" / "test-skill.md"
        self.assertTrue(out.exists())
        self.assertIn("name: test-skill", out.read_text(encoding="utf-8"))

    def test_pattern_key_recurrence(self):
        for _ in range(2):
            run_cli(["log", "--pattern-key", "same-issue", "--message", "again"], self.dir)
        r = run_cli(["log", "--pattern-key", "same-issue", "--message", "third"], self.dir)
        self.assertIn("已出现 3 次", r.stdout)

    def test_remember_degrade_A(self):
        """未安装 yotta-memory：降级 A，本地记录不阻断。"""
        env = {"PATH": str(self.dir / "empty-bin")}
        r = run_cli(["log", "--message", "local only", "--remember"], self.dir, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("未安装", r.stdout)
        self.assertTrue((self.dir / ".learnings" / "LEARNINGS.md").exists())

    def test_remember_degrade_B(self):
        """已安装但不可用：降级 B，不阻断。"""
        bin_dir = self.dir / "fakebin"
        make_fake_ym(bin_dir, "fail")
        env = {"PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", "")}
        r = run_cli(["log", "--message", "degrade B", "--remember"], self.dir, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("未初始化", r.stdout)

    def test_remember_degrade_C(self):
        """探测超时：降级 C，不阻断。"""
        bin_dir = self.dir / "fakebin"
        make_fake_ym(bin_dir, "timeout")
        env = {"PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", "")}
        r = run_cli(["log", "--message", "degrade C", "--remember"], self.dir, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("超时", r.stdout)

    def test_remember_ok(self):
        """元忆可用：同步成功，本地记录仍在。"""
        bin_dir = self.dir / "fakebin"
        make_fake_ym(bin_dir, "ok")
        env = {"PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", "")}
        r = run_cli(["log", "--message", "sync ok", "--remember"], self.dir, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("已同步", r.stdout)

    def test_gbk_console_no_crash(self):
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "gbk"
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "init"],
            capture_output=True, cwd=str(self.dir), env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr.decode("gbk", errors="replace"))
        self.assertNotIn(b"UnicodeEncodeError", r.stderr)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    ok = unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
    sys.exit(0 if ok else 1)

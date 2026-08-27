#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yotta_learn.py — YottaMeta 元习（yotta-learn）学习闭环 CLI。

把错误、纠正与洞见沉淀为 .learnings/ 条目，供后续会话与技能改进复用；
CLI 全跨平台（Windows + Linux），纯 Python 3.8+ 标准库，零外部依赖。

子命令：
  init     初始化 .learnings/（绝不覆盖已存在文件）
  log      新建条目（自动 ID + ISO 时间戳；--remember 可选联动元忆）
  list     按 category/priority/status/area 过滤列出
  promote  提升到 AGENTS.md / CLAUDE.md（自动去重）
  review   回看待处理条目
  stats    统计
  extract  由条目生成技能骨架

exit code：0 = 成功；1 = 未找到/无事可做；4 = 用法错误/致命异常。

用法示例：
  python3 yotta_learn.py init
  python3 yotta_learn.py log --type error --category correction \\
      --priority high --message "接口超时重试导致重复提交"
  python3 yotta_learn.py list --status pending
  python3 yotta_learn.py promote LRN-20260826-001
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
try:
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

VERSION = "0.1.3"
TOOL_NAME = "yotta-learn"

# 类型 → (ID 前缀, 文件名, 显示名)
TYPES = {
    "learning": ("LRN", "LEARNINGS.md", "学习"),
    "error": ("ERR", "ERRORS.md", "错误"),
    "feature": ("FEAT", "FEATURE_REQUESTS.md", "功能需求"),
}
TYPE_ORDER = ("learning", "error", "feature")
CATEGORIES = ("correction", "insight", "knowledge_gap", "best_practice", "error", "other")
PRIORITIES = ("low", "medium", "high", "critical")
STATUSES = ("pending", "in_progress", "resolved", "wont_fix", "promoted", "promoted_to_skill")

ENTRY_RE = re.compile(r"^##\s+\[([A-Z]+-\d{8}-\d{3})\]\s+([a-z_]+)\s*$")
FIELD_RE = re.compile(r"^\*\*([A-Za-z][A-Za-z -]*)\*\*:\s*(.*)$")
SUMMARY_RE = re.compile(r"^###\s+Summary\s*$", re.I)
DETAILS_RE = re.compile(r"^###\s+Details\s*$", re.I)
RESOLUTION_RE = re.compile(r"^###\s+Resolution\s*$", re.I)

LEARNINGS_DIR_NAME = ".learnings"
DEFAULT_FILES = {
    "LEARNINGS.md": "# Learnings\n\nCorrections, insights, and knowledge gaps captured during development.\n\n**Categories**: correction | insight | knowledge_gap | best_practice | error | other\n\n---\n",
    "ERRORS.md": "# Errors\n\nCommand failures and integration errors.\n\n---\n",
    "FEATURE_REQUESTS.md": "# Feature Requests\n\nCapabilities requested by the user.\n\n---\n",
}

# ── 目录与原子写 ────────────────────────────────────────────────────────────

def learnings_dir(explicit=None):
    """解析 .learnings 目录：--dir 优先，否则 cwd。"""
    if explicit:
        return Path(explicit).resolve()
    return (Path.cwd() / LEARNINGS_DIR_NAME).resolve()


def ensure_init(directory):
    """初始化 .learnings/（幂等，绝不覆盖已存在文件）。"""
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in DEFAULT_FILES.items():
        p = directory / name
        if not p.exists():
            _atomic_write_text(p, content)
    return directory


def _atomic_write_text(path, text):
    """原子写：临时文件 + os.replace，避免并发写丢条目。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".ytl-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_text(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ── 条目模型 ────────────────────────────────────────────────────────────────

class Entry:
    def __init__(self, eid, kind, category, file_path, line, fields, summary, body):
        self.eid = eid          # LRN-20260826-001
        self.kind = kind        # learning / error / feature
        self.category = category  # correction / ...
        self.file_path = file_path
        self.line = line
        self.fields = fields    # {Field: value}
        self.summary = summary
        self.body = body

    def field(self, name, default=""):
        return self.fields.get(name, default)

    @property
    def logged(self):
        return self.field("Logged", "")

    @property
    def priority(self):
        return self.field("Priority", "medium").lower()

    @property
    def status(self):
        return self.field("Status", "pending").lower()

    @property
    def area(self):
        return self.field("Area", "")

    @property
    def pattern_key(self):
        return self.field("Pattern-Key", "")

    _PRIORITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    _STATUS_RANK = {"pending": 0, "in_progress": 1, "resolved": 2,
                    "wont_fix": 3, "promoted": 4, "promoted_to_skill": 5}

    def priority_rank(self):
        return self._PRIORITY_RANK.get(self.priority, 1)

    def status_rank(self):
        return self._STATUS_RANK.get(self.status, 0)

    def to_dict(self):
        return {
            "id": self.eid, "type": self.kind, "category": self.category,
            "logged": self.logged, "priority": self.priority,
            "status": self.status, "area": self.area,
            "pattern_key": self.pattern_key, "summary": self.summary,
            "file": str(self.file_path), "line": self.line,
        }


def parse_entries(directory):
    """解析 .learnings/ 三个文件，返回 [Entry]（含旧格式兼容，解析不了的行跳过不崩）。"""
    entries = []
    for kind in TYPE_ORDER:
        prefix, fname, _ = TYPES[kind]
        p = directory / fname
        if not p.exists():
            continue
        content = _read_text(p)
        lines = content.splitlines()
        i = 0
        n = len(lines)
        while i < n:
            m = ENTRY_RE.match(lines[i])
            if not m:
                i += 1
                continue
            eid, category = m.group(1), m.group(2)
            if not eid.startswith(prefix):
                i += 1
                continue
            start_line = i + 1
            fields = {}
            summary = ""
            body_parts = []
            j = i + 1
            in_summary = False
            in_details = False
            while j < n:
                if ENTRY_RE.match(lines[j]):
                    break
                fm = FIELD_RE.match(lines[j])
                if fm:
                    fields[fm.group(1)] = fm.group(2).strip()
                    in_summary = False
                    in_details = False
                    j += 1
                    continue
                if SUMMARY_RE.match(lines[j]):
                    in_summary, in_details = True, False
                    j += 1
                    continue
                if DETAILS_RE.match(lines[j]):
                    in_summary, in_details = False, True
                    j += 1
                    continue
                if RESOLUTION_RE.match(lines[j]):
                    in_summary, in_details = False, False
                    j += 1
                    continue
                if lines[j].strip():
                    if in_summary and not summary:
                        summary = lines[j].strip()
                    elif in_details:
                        body_parts.append(lines[j].rstrip())
                j += 1
            entries.append(Entry(
                eid=eid, kind=kind, category=category, file_path=p,
                line=start_line, fields=fields, summary=summary,
                body="\n".join(body_parts),
            ))
            i = j
    return entries


def find_entry(entries, eid):
    for e in entries:
        if e.eid.lower() == eid.lower():
            return e
    return None

# ── 写入（log）──────────────────────────────────────────────────────────────

def next_id(directory, kind):
    """按类型生成下一个 ID：LRN/ERR/FEAT-YYYYMMDD-XXX。"""
    prefix, _, _ = TYPES[kind]
    today = datetime.now().strftime("%Y%m%d")
    used = set()
    for e in parse_entries(directory):
        if e.eid.startswith(prefix + "-" + today):
            used.add(e.eid)
    seq = 1
    while "%s-%s-%03d" % (prefix, today, seq) in used:
        seq += 1
    return "%s-%s-%03d" % (prefix, today, seq)


def build_entry_markdown(eid, kind, category, priority, status, area, pattern_key, message):
    """生成单条条目 markdown（含 ID 与时间戳）。"""
    lines = []
    lines.append("## [%s] %s" % (eid, category))
    lines.append("")
    lines.append("**Logged**: %s" % datetime.now().astimezone().isoformat(timespec="seconds"))
    lines.append("**Priority**: %s" % priority)
    lines.append("**Status**: %s" % status)
    if area:
        lines.append("**Area**: %s" % area)
    if pattern_key:
        lines.append("**Pattern-Key**: %s" % pattern_key)
    lines.append("")
    lines.append("### Summary")
    msg_lines = [l for l in message.strip().splitlines() if l.strip()]
    lines.append(msg_lines[0] if msg_lines else "")
    if len(msg_lines) > 1:
        lines.append("")
        lines.append("### Details")
        lines.append("\n".join(msg_lines[1:]))
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def append_entry(directory, kind, category, priority, status, area, pattern_key, message):
    """追加条目（原子写），返回新条目 ID。"""
    directory = ensure_init(directory)
    eid = next_id(directory, kind)
    text = build_entry_markdown(eid, kind, category, priority, status,
                                area, pattern_key, message)
    _, fname, _ = TYPES[kind]
    p = directory / fname
    old = _read_text(p)
    if not old.endswith("\n"):
        old += "\n"
    _atomic_write_text(p, old + text)
    return eid


# ── yotta-memory 联动（L3，可选 + 自动降级 A/B/C）─────────────────────────

def probe_yotta_memory(timeout=10):
    """探测元忆可用性，返回 ('ok'|'A'|'B'|'C', 说明)。"""
    exe = shutil.which("yotta-memory")
    if exe is None:
        return "A", "未安装 yotta-memory（本地记录不受影响）"
    try:
        r = subprocess.run([exe, "whoami"], capture_output=True, timeout=timeout,
                           text=True, errors="replace")
    except subprocess.TimeoutExpired:
        return "C", "yotta-memory 探测超时"
    except OSError as e:
        return "C", "yotta-memory 运行失败: %s" % e
    if r.returncode == 0 and r.stdout.strip():
        return "ok", ""
    if "not initialized" in (r.stderr or "").lower() or "未初始化" in (r.stderr or ""):
        return "B", "yotta-memory 未初始化（本地记录不受影响）"
    return "B", "yotta-memory 不可用（%s）" % (r.stderr or r.stdout or "未知原因").strip()[:120]


def remember_to_yotta_memory(summary, area, kind, category, directory, timeout=20):
    """把条目同步到元忆；任何失败都降级，绝不阻断本地写入。"""
    probe, note = probe_yotta_memory()
    if probe != "ok":
        return probe, note
    try:
        exe = shutil.which("yotta-memory")
        # 先 search 去重（元忆 search 无结果或出错都不影响）
        try:
            sr = subprocess.run([exe, "search", "--query", summary[:80]],
                                capture_output=True, timeout=timeout,
                                text=True, errors="replace")
            if sr.returncode == 0 and summary[:40] in (sr.stdout or ""):
                return "dedup", "元忆已存在相似记忆，跳过同步"
        except (subprocess.TimeoutExpired, OSError):
            pass
        stmt = "[%s] %s" % (category, summary)
        rr = subprocess.run([exe, "remember", "--type", "FACT" if kind != "error" else "PREF",
                             "--subject", "yotta-learn: %s" % area if area else "yotta-learn",
                             "--statement", stmt],
                            capture_output=True, timeout=timeout,
                            text=True, errors="replace")
        if rr.returncode == 0:
            return "ok", "已同步到元忆"
        return "B", "元忆 remember 失败（%s）" % (rr.stderr or "").strip()[:120]
    except (subprocess.TimeoutExpired, OSError) as e:
        return "C", "元忆联动失败: %s" % e

# ── 查询与动作 ──────────────────────────────────────────────────────────────

def cmd_init(args):
    directory = learnings_dir(args.dir)
    ensure_init(directory)
    print("已初始化 %s（已存在文件未改动）" % directory)
    return 0


def cmd_log(args):
    directory = learnings_dir(args.dir)
    kind = args.type
    category = args.category or ("error" if kind == "error" else "insight")
    if category not in CATEGORIES:
        print("[ERROR] 无效 category: %s（可用: %s）" % (category, " | ".join(CATEGORIES)),
              file=sys.stderr)
        return 4
    message = args.message or ""
    if not message.strip():
        print("[ERROR] --message 不能为空", file=sys.stderr)
        return 4
    eid = append_entry(directory, kind, category, args.priority, args.status,
                       args.area, args.pattern_key, message)
    print("已记录 %s -> %s" % (eid, directory / TYPES[kind][1]))

    # 复发模式追踪（L4）：同 Pattern-Key >= 2 提示合并 + 提权
    if args.pattern_key:
        same = [e for e in parse_entries(directory)
                if e.pattern_key == args.pattern_key]
        if len(same) >= 2:
            print("[提示] Pattern-Key '%s' 已出现 %d 次，建议合并为一条并提升优先级"
                  % (args.pattern_key, len(same)))

    # 元忆联动（L3）：--remember 显式开启；降级 A/B/C 不阻断本地记录
    if args.remember:
        code, note = remember_to_yotta_memory(
            message.strip().splitlines()[0], args.area, kind, category, directory)
        print("[元忆] %s" % note if note else "[元忆] 已同步")
    return 0


def cmd_list(args):
    directory = learnings_dir(args.dir)
    entries = parse_entries(directory)
    if args.type:
        entries = [e for e in entries if e.kind == args.type]
    if args.category:
        entries = [e for e in entries if e.category == args.category]
    if args.priority:
        entries = [e for e in entries if e.priority == args.priority]
    if args.status:
        entries = [e for e in entries if e.status == args.status]
    if args.area:
        entries = [e for e in entries if args.area.lower() in e.area.lower()]
    entries.sort(key=lambda e: (e.logged, e.eid), reverse=True)
    if args.json:
        print(json.dumps([e.to_dict() for e in entries], indent=2, ensure_ascii=False))
        return 0
    if not entries:
        print("（无匹配条目）")
        return 0
    for e in entries:
        print("%-18s %-11s %-9s %-8s %-10s %s" % (
            e.eid, e.kind, e.priority, e.status, e.area or "-", e.summary or "(无摘要)"))
    print("共 %d 条" % len(entries))
    return 0


def cmd_promote(args):
    directory = learnings_dir(args.dir)
    entries = parse_entries(directory)
    entry = find_entry(entries, args.id)
    if entry is None:
        print("[ERROR] 未找到条目: %s" % args.id, file=sys.stderr)
        return 1
    target_name = args.to
    if not target_name or target_name == "auto":
        target_name = "CLAUDE.md" if (directory / "CLAUDE.md").exists() else "AGENTS.md"
    target = directory / target_name
    block = "\n".join([
        "## 学习记录 %s [%s] %s" % (entry.eid, entry.priority, entry.category),
        "",
        "- **Logged**: %s" % (entry.logged or "-"),
        "- **Area**: %s" % (entry.area or "-"),
        "- **Summary**: %s" % (entry.summary or "-"),
        "- **Details**:",
    ])
    if entry.body:
        block += "\n" + "\n".join("  " + line for line in entry.body.splitlines())
    block += "\n"
    old = _read_text(target)
    if entry.summary and entry.summary[:60] in old:
        print("[提示] 目标文件已包含相似内容，跳过（自动去重）")
        return 0
    if not old.endswith("\n"):
        old += "\n"
    _atomic_write_text(target, old + block + "\n")
    # 更新条目状态为 promoted
    _update_entry_status(directory, entry, "promoted", target_name)
    print("已提升 %s -> %s" % (entry.eid, target))
    return 0


def _update_entry_status(directory, entry, new_status, target_name):
    """把条目 **Status** 更新为 promoted，并记录 Promoted-To。"""
    p = Path(entry.file_path)
    content = _read_text(p)
    lines = content.splitlines()
    out = []
    in_entry = False
    for line in lines:
        if ENTRY_RE.match(line):
            in_entry = line.startswith("[" + entry.eid.split("-", 1)[0] + "-")
            if in_entry:
                in_entry = line.startswith("## [" + entry.eid + "]")
        if in_entry and line.startswith("**Status**:"):
            out.append("**Status**: %s" % new_status)
            continue
        if in_entry and line.startswith("**Promoted-To**:"):
            continue
        out.append(line)
    text = "\n".join(out)
    # 在 Summary 前插入 Promoted-To 字段
    marker = "### Summary"
    if marker in text:
        idx = text.index(marker)
        insert = "\n**Promoted-To**: %s\n" % target_name
        text = text[:idx] + insert + text[idx:]
    _atomic_write_text(p, text)


def cmd_review(args):
    directory = learnings_dir(args.dir)
    entries = [e for e in parse_entries(directory)
               if e.status in ("pending", "in_progress")]
    entries.sort(key=lambda e: (e.priority_rank(), e.logged))
    if not entries:
        print("（无待处理条目）")
        return 0
    for e in entries:
        print("%-18s %-9s %-8s %s" % (e.eid, e.priority, e.status, e.summary or "-"))
    print("待处理 %d 条" % len(entries))
    return 0


def cmd_stats(args):
    directory = learnings_dir(args.dir)
    entries = parse_entries(directory)
    total = len(entries)
    by_type = {}
    by_status = {}
    by_priority = {}
    by_area = {}
    pattern_counts = {}
    for e in entries:
        by_type[e.kind] = by_type.get(e.kind, 0) + 1
        by_status[e.status] = by_status.get(e.status, 0) + 1
        by_priority[e.priority] = by_priority.get(e.priority, 0) + 1
        if e.area:
            by_area[e.area] = by_area.get(e.area, 0) + 1
        if e.pattern_key:
            pattern_counts[e.pattern_key] = pattern_counts.get(e.pattern_key, 0) + 1
    print("yotta-learn 统计（%s）" % directory)
    print("  总条目: %d" % total)
    print("  类型: %s" % ", ".join("%s=%d" % (k, v) for k, v in sorted(by_type.items())))
    print("  状态: %s" % ", ".join("%s=%d" % (k, v) for k, v in sorted(by_status.items())))
    print("  优先级: %s" % ", ".join("%s=%d" % (k, v) for k, v in sorted(by_priority.items())))
    if by_area:
        print("  领域: %s" % ", ".join("%s=%d" % (k, v) for k, v in sorted(by_area.items())))
    recurrent = {k: v for k, v in pattern_counts.items() if v >= 2}
    if recurrent:
        print("  复发模式(>=2): %s" % ", ".join("%s=%d" % (k, v) for k, v in sorted(recurrent.items())))
    return 0

# ── extract（生成技能骨架）─────────────────────────────────────────────────

SKILL_TEMPLATE = """---
name: {slug}
description: "{description}"
---

# {title}

{summary}

## Source

- Learning ID: {learning_id}
- Category: {category}
- Area: {area}
- Extracted: {date}
"""


def _slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:60] or "new-skill"


def cmd_extract(args):
    directory = learnings_dir(args.dir)
    entries = parse_entries(directory)
    entry = find_entry(entries, args.id)
    if entry is None:
        print("[ERROR] 未找到条目: %s" % args.id, file=sys.stderr)
        return 1
    slug = _slugify(args.slug or (entry.area or entry.summary or entry.category))
    description = entry.summary or ("源自学习条目 %s" % entry.eid)
    content = SKILL_TEMPLATE.format(
        slug=slug,
        description=description[:180],
        title=slug.replace("-", " ").title(),
        summary=entry.summary or "",
        learning_id=entry.eid,
        category=entry.category,
        area=entry.area or "-",
        date=datetime.now().strftime("%Y-%m-%d"),
    )
    if args.dry_run:
        print(content)
        print("[dry-run] 未写入文件")
        return 0
    out_dir = Path(args.out) if args.out else directory / "extracted-skills"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / (slug + ".md")
    _atomic_write_text(out_file, content)
    print("已生成技能骨架 -> %s" % out_file)
    # 标记原条目为 promoted_to_skill
    _update_entry_status(directory, entry, "promoted_to_skill", str(out_file.relative_to(directory)))
    print("条目 %s 已标记为 promoted_to_skill" % entry.eid)
    return 0


# ── 参数解析与入口 ──────────────────────────────────────────────────────────

class _LearnParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(4, "%s: error: %s\\n" % (self.prog, message))


def build_parser():
    ap = _LearnParser(prog=TOOL_NAME, description="YottaMeta 元习 —— 学习闭环 CLI")
    sub = ap.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="初始化 .learnings/")
    p_init.add_argument("--dir", help=".learnings 所在目录（默认当前目录）")

    p_log = sub.add_parser("log", help="新建学习条目")
    p_log.add_argument("--type", choices=list(TYPES.keys()), default="learning")
    p_log.add_argument("--category", choices=CATEGORIES)
    p_log.add_argument("--priority", choices=PRIORITIES, default="medium")
    p_log.add_argument("--status", choices=STATUSES, default="pending")
    p_log.add_argument("--area", default="")
    p_log.add_argument("--pattern-key", default="")
    p_log.add_argument("--message", default="")
    p_log.add_argument("--remember", action="store_true", help="同步到 yotta-memory（可选）")
    p_log.add_argument("--dir")

    p_list = sub.add_parser("list", help="列出条目")
    p_list.add_argument("--type", choices=list(TYPES.keys()))
    p_list.add_argument("--category")
    p_list.add_argument("--priority")
    p_list.add_argument("--status")
    p_list.add_argument("--area")
    p_list.add_argument("--json", action="store_true")
    p_list.add_argument("--dir")

    p_promote = sub.add_parser("promote", help="提升条目到 AGENTS.md/CLAUDE.md")
    p_promote.add_argument("id")
    p_promote.add_argument("--to", help="目标文件（默认 auto：CLAUDE.md 优先）")
    p_promote.add_argument("--dir")

    p_review = sub.add_parser("review", help="回看待处理条目")
    p_review.add_argument("--dir")

    p_stats = sub.add_parser("stats", help="统计")
    p_stats.add_argument("--dir")

    p_extract = sub.add_parser("extract", help="由条目生成技能骨架")
    p_extract.add_argument("id")
    p_extract.add_argument("--slug")
    p_extract.add_argument("--out")
    p_extract.add_argument("--dry-run", action="store_true")
    p_extract.add_argument("--dir")

    return ap


COMMANDS = {
    "init": cmd_init,
    "log": cmd_log,
    "list": cmd_list,
    "promote": cmd_promote,
    "review": cmd_review,
    "stats": cmd_stats,
    "extract": cmd_extract,
}


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    cmd = COMMANDS.get(args.command)
    if cmd is None:
        ap.error("未知命令: %s" % args.command)
    try:
        return cmd(args)
    except OSError as e:
        print("[ERROR] 文件操作失败: %s" % e, file=sys.stderr)
        return 4


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except KeyboardInterrupt:
        sys.exit(4)
    except Exception as e:
        print("[FATAL] %s: %s" % (TOOL_NAME, e), file=sys.stderr)
        sys.exit(4)

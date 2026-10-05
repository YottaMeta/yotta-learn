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

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
try:
    import yotta_kb
    import yotta_kb_index
except ImportError as _kb_import_error:  # pragma: no cover - 仅在包不完整时触发
    print("[ERROR] 元习组件缺失（%s）：请用官方安装器重装完整技能包" % _kb_import_error,
          file=sys.stderr)
    sys.exit(4)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
try:
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

VERSION = "0.3.0"
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


# ── 条目块级编辑（update / resolve / promote / extract 共用）────────────────

def _block_last_field_index(block):
    idx = None
    for k, line in enumerate(block):
        if FIELD_RE.match(line):
            idx = k
    return idx if idx is not None else 0


def _set_field(block, key, value):
    pat = "**%s**:" % key
    for k, line in enumerate(block):
        if line.startswith(pat):
            block[k] = "%s %s" % (pat, value)
            return
    block.insert(_block_last_field_index(block) + 1, "%s %s" % (pat, value))


def _remove_field(block, key):
    pat = "**%s**:" % key
    block[:] = [line for line in block if not line.startswith(pat)]


def edit_entry_text(content, eid, status=None, priority=None, note=None, extra_fields=None):
    """对指定条目块做字段 / Resolution 编辑；未找到条目返回 None。

    块边界 = 本条目标题行到下一个条目标题行（或文件末尾），因此多条目
    文件里第 2+ 条的编辑不会误改到第 1 条（历史缺陷回归）。
    """
    lines = content.splitlines()
    start = None
    for i, line in enumerate(lines):
        m = ENTRY_RE.match(line)
        if m and m.group(1).lower() == eid.lower():
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if ENTRY_RE.match(lines[j]):
            end = j
            break
    block = lines[start:end]
    if status:
        _set_field(block, "Status", status)
    if priority:
        _set_field(block, "Priority", priority)
    for key, value in (extra_fields or {}).items():
        _remove_field(block, key)
        _set_field(block, key, value)
    if note and note.strip():
        note_line = "- %s %s" % (datetime.now().strftime("%Y-%m-%d"), note.strip())
        rstart = None
        for k, line in enumerate(block):
            if RESOLUTION_RE.match(line):
                rstart = k
                break
        if rstart is not None:
            rend = len(block)
            for j in range(rstart + 1, len(block)):
                if re.match(r"^###\s+", block[j]) or block[j].strip() == "---":
                    rend = j
                    break
            insert_at = rend
            while insert_at > rstart + 1 and not block[insert_at - 1].strip():
                insert_at -= 1
            block.insert(insert_at, note_line)
        else:
            sep = None
            for k in range(len(block) - 1, -1, -1):
                if block[k].strip() == "---":
                    sep = k
                    break
            insert_at = sep if sep is not None else len(block)
            while insert_at > 0 and not block[insert_at - 1].strip():
                insert_at -= 1
            block[insert_at:insert_at] = ["", "### Resolution", "", note_line, ""]
    new_lines = lines[:start] + block + lines[end:]
    text = "\n".join(new_lines)
    if content.endswith("\n"):
        text += "\n"
    return text


def _update_entry_status(directory, entry, new_status, target_name):
    """把条目 **Status** 更新为新状态，并记录 Promoted-To（块级编辑）。"""
    p = Path(entry.file_path)
    content = _read_text(p)
    new = edit_entry_text(content, entry.eid, status=new_status,
                          extra_fields={"Promoted-To": target_name})
    if new is None:
        raise OSError("未找到条目块: %s" % entry.eid)
    _atomic_write_text(p, new)


def _apply_entry_update(directory, eid, status, priority, note):
    entries = parse_entries(directory)
    entry = find_entry(entries, eid)
    if entry is None:
        print("[ERROR] 未找到条目: %s" % eid, file=sys.stderr)
        return 1
    if not (status or priority or note):
        print("[ERROR] update 需要 --status / --priority / --note 至少一项", file=sys.stderr)
        return 4
    changes = []
    if status and status != entry.status:
        changes.append("status: %s -> %s" % (entry.status, status))
    if priority and priority != entry.priority:
        changes.append("priority: %s -> %s" % (entry.priority, priority))
    if note:
        changes.append("note 已追加到 Resolution")
    new = edit_entry_text(_read_text(Path(entry.file_path)), entry.eid,
                          status=status, priority=priority, note=note)
    if new is None:
        print("[ERROR] 未找到条目块: %s" % eid, file=sys.stderr)
        return 1
    _atomic_write_text(Path(entry.file_path), new)
    print("已更新 %s：%s" % (entry.eid, "；".join(changes) or "无变化"))
    return 0


def cmd_update(args):
    return _apply_entry_update(learnings_dir(args.dir), args.id,
                               args.status, args.priority, args.note)


def cmd_resolve(args):
    return _apply_entry_update(learnings_dir(args.dir), args.id,
                               "resolved", None, args.note)


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


# ── 知识库（kb）命令 ────────────────────────────────────────────────────────

def _kb_root(args):
    return yotta_kb.resolve_kb_root(getattr(args, "dir", None))


def _kb_require(args):
    root, _source = _kb_root(args)
    yotta_kb.load_kb(root)
    return root


def _kb_actor(args):
    actor = yotta_kb.resolve_actor(getattr(args, "agent", None))
    if yotta_kb.actor_is_unknown(actor):
        print("[提示] 未检测到智能体身份（--agent 或环境变量 YOTTA_LEARN_AGENT），记为 %s"
              % actor)
    return actor


def _kb_out_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _kb_resolve_cat(root, slug):
    if not slug:
        return None
    return yotta_kb.resolve_category(root, slug)["slug"]


def _kb_parse_list(values):
    out = []
    for chunk in (values or []):
        out.extend([v.strip() for v in str(chunk).split(",") if v.strip()])
    return out


def _kb_init(args):
    root, source = _kb_root(args)
    actor = _kb_actor(args)
    yotta_kb.init_kb(root, actor)
    print("已初始化知识库：%s（来源: %s）" % (root, source))
    print("下一步: yotta-learn kb category create <slug> --name '中文名' --description '一句话说明'")
    return 0


def _kb_config_set(args):
    target = Path(args.path).expanduser().resolve()
    cfg = yotta_kb.load_config()
    cfg["kbDir"] = str(target)
    cfg["updated_at"] = yotta_kb.now_iso()
    yotta_kb.save_config(cfg)
    print("已写入配置：%s" % yotta_kb.config_path())
    print("  kbDir = %s" % target)
    return 0


def _kb_config_get(args):
    root, source = _kb_root(args)
    print("KB 根目录: %s" % root)
    print("来源: %s" % {"flag": "--dir", "env": "YOTTA_LEARN_KB",
                        "config": "配置文件", "default": "默认"}.get(source, source))
    if yotta_kb.is_initialized(root):
        kb_meta = yotta_kb.load_kb(root)
        print("库状态: 已初始化（schema %s，%d 条条目）"
              % (kb_meta.get("schema"), yotta_kb.count_entries(root)))
    else:
        print("库状态: 未初始化（运行 yotta-learn kb init）")
    return 0


def _kb_config_clear(args):
    p = yotta_kb.config_path()
    if p.exists():
        p.unlink()
        print("已清除配置：%s" % p)
    else:
        print("配置文件不存在（无需清除）：%s" % p)
    return 0


def _kb_category_create(args):
    root = _kb_require(args)
    actor = _kb_actor(args)
    cat = yotta_kb.create_category(root, args.slug, args.name, args.description,
                                   args.alias or [], actor)
    print("已创建分类 %s（%s）" % (cat["slug"], cat["name"]))
    return 0


def _kb_category_list(args):
    root = _kb_require(args)
    cats = yotta_kb.list_categories(root)
    if args.json:
        _kb_out_json(cats)
        return 0
    if not cats:
        print("（暂无分类）")
        return 0
    for cat in cats:
        flag = "" if cat.get("status") == "active" else " [%s]" % cat.get("status")
        aliases = ("  别名: %s" % ", ".join(cat.get("aliases", []))) if cat.get("aliases") else ""
        print("%-24s %-16s%s %s%s"
              % (cat["slug"], cat["name"], flag, cat["description"], aliases))
    print("共 %d 个分类" % len(cats))
    return 0


def _kb_category_rename(args):
    root = _kb_require(args)
    actor = _kb_actor(args)
    cat = yotta_kb.rename_category(root, args.slug, args.name, actor)
    print("已重命名分类 %s -> %s" % (cat["slug"], cat["name"]))
    return 0


def _kb_category_merge(args):
    root = _kb_require(args)
    actor = _kb_actor(args)
    result = yotta_kb.merge_category(root, args.slug, args.into, actor)
    print("已合并分类 %s -> %s（迁移 %d 条；%s 变为别名）"
          % (result["from"], result["into"], result["moved"], result["from"]))
    return 0


def _kb_category_deprecate(args):
    root = _kb_require(args)
    actor = _kb_actor(args)
    cat = yotta_kb.deprecate_category(root, args.slug, actor,
                                      reason=args.reason or "", force=args.force)
    print("已停用分类 %s（%s）" % (cat["slug"], cat["name"]))
    return 0


def _kb_add(args):
    root = _kb_require(args)
    actor = _kb_actor(args)
    tags = _kb_parse_list(args.tags)
    entry = yotta_kb.add_entry(root, args.category, args.title, args.message,
                               tags, args.source, args.evidence,
                               args.confidence, actor)
    text = "\n".join([entry.title, " ".join(entry.tags), entry.body])
    findings = yotta_kb.scan_sensitive(text)
    similar = yotta_kb.similar_titles(root, entry)
    if args.json:
        _kb_out_json({
            "id": entry.id, "path": str(entry.path), "status": entry.status,
            "category": entry.category, "sensitive": findings, "similar": similar,
        })
        return 0
    print("已写入草稿 %s -> %s" % (entry.id, entry.path))
    if findings:
        kinds = ", ".join(sorted(set(f["kind"] for f in findings)))
        print("[敏感] 命中 %d 处（%s）：review 通过将被阻断，需 --force --note 放行"
              % (len(findings), kinds))
    if similar:
        print("[查重] 标题相近：%s"
              % ", ".join("%s(%.2f)" % (s["id"], s["similarity"]) for s in similar))
    print("下一步: yotta-learn kb review %s（三问清单）" % entry.id)
    return 0


def _kb_list(args):
    root = _kb_require(args)
    cat_slug = _kb_resolve_cat(root, args.category)
    tags = [t.lower() for t in _kb_parse_list(args.tag)]
    entries = []
    for entry in yotta_kb.iter_entries(root, category=cat_slug):
        if args.status and entry.status != args.status:
            continue
        if tags and not any(t in [x.lower() for x in entry.tags] for t in tags):
            continue
        entries.append(entry)
    entries.sort(key=lambda e: (e.updated, e.id), reverse=True)
    if args.limit and args.limit > 0:
        entries = entries[:args.limit]
    if args.json:
        _kb_out_json([e.to_dict() for e in entries])
        return 0
    if not entries:
        print("（无匹配条目）")
        return 0
    for entry in entries:
        print("%-18s %-10s %-8s %-20s %s"
              % (entry.id, entry.status, entry.confidence, entry.category, entry.title))
    print("共 %d 条" % len(entries))
    return 0


def _kb_show(args):
    root = _kb_require(args)
    entry = yotta_kb.find_entry(root, args.id)
    if entry is None:
        raise yotta_kb.KbNotFound("未找到条目：%s" % args.id)
    if args.json:
        _kb_out_json(entry.to_dict(include_body=True))
        return 0
    print("ID: %s" % entry.id)
    print("标题: %s" % entry.title)
    print("分类: %s" % entry.category)
    print("状态: %s / confidence: %s" % (entry.status, entry.confidence))
    print("标签: %s" % (", ".join(entry.tags) or "-"))
    print("出处: %s" % (entry.fields.get("source") or "-"))
    print("证据: %s" % (entry.fields.get("evidence") or "-"))
    print("作者: %s / 创建: %s / 更新: %s"
          % (entry.fields.get("author") or "-", entry.fields.get("created") or "-",
             entry.fields.get("updated") or "-"))
    if entry.fields.get("verified_by"):
        print("核验: %s @ %s" % (entry.fields.get("verified_by"), entry.fields.get("verified_at")))
    print("路径: %s" % entry.path)
    print("")
    print(entry.body)
    return 0


def _kb_update(args):
    root = _kb_require(args)
    actor = _kb_actor(args)
    changes = {}
    if args.title is not None:
        changes["title"] = args.title
    if args.message is not None:
        changes["message"] = args.message
    if args.tags is not None:
        changes["tags"] = _kb_parse_list(args.tags)
    if args.source is not None:
        changes["source"] = args.source
    if args.evidence is not None:
        changes["evidence"] = args.evidence
    if args.confidence is not None:
        changes["confidence"] = args.confidence
    entry = yotta_kb.update_entry(root, args.id, changes, actor)
    print("已更新 %s（字段: %s）" % (entry.id, ", ".join(sorted(changes.keys()))))
    return 0


def _kb_deprecate(args):
    root = _kb_require(args)
    actor = _kb_actor(args)
    entry = yotta_kb.deprecate_entry(root, args.id, args.reason, actor)
    print("已停用条目 %s（原因已记入审计）" % entry.id)
    return 0


def _kb_review(args):
    root = _kb_require(args)
    if not args.pass_ and not args.reject:
        entry = yotta_kb.find_entry(root, args.id)
        if entry is None:
            raise yotta_kb.KbNotFound("未找到条目：%s" % args.id)
        print("质检三问（%s）：" % entry.id)
        print("  1) 验证过？—— 有可验证的证据（--evidence）")
        print("  2) 自包含？—— 不依赖会话上下文即可复用")
        print("  3) 无敏感？—— 无密钥 / 个人信息 / 本机路径")
        print("当前证据: %s" % (entry.fields.get("evidence") or "（无）"))
        print("下一步: --pass 核验 / --reject --note '原因'")
        return 0
    actor = _kb_actor(args)
    decision = "pass" if args.pass_ else "reject"
    entry, extra = yotta_kb.review_entry(root, args.id, decision, args.note,
                                         args.evidence, actor, force=args.force)
    if decision == "pass":
        print("已核验 %s（%s）" % (entry.id, entry.title))
        if extra.get("findings"):
            print("[敏感] --force 放行 %d 处命中（已记审计）" % len(extra["findings"]))
        if extra.get("similar"):
            print("[查重] 标题相近：%s"
                  % ", ".join("%s(%.2f)" % (s["id"], s["similarity"])
                              for s in extra["similar"]))
    else:
        print("已拒绝 %s 并移入回收站" % entry.id)
    return 0


def _kb_query(args):
    root = _kb_require(args)
    statuses = _kb_parse_list([args.status]) if args.status else None
    tags = _kb_parse_list(args.tag)
    result = yotta_kb_index.query(
        root, " ".join(args.keywords), category=args.category, statuses=statuses,
        tags=tags, limit=args.limit, include_draft=args.include_draft,
        include_deprecated=args.include_deprecated)
    if args.json:
        _kb_out_json(result)
        return 0
    if result["stale"]:
        print("[警告] 索引漂移，已降级线性扫描；建议运行 kb index rebuild")
    if not result["results"]:
        print("（无匹配结果）")
        return 0
    for item in result["results"]:
        print("%8.2f  %-18s [%-10s] %s (%s)"
              % (item["score"], item["id"], item["status"], item["title"],
                 item["category"]))
    print("共 %d 条（显示 %d；模式: %s）"
          % (result["count"], len(result["results"]), result["mode"]))
    return 0


def _kb_index_rebuild(args):
    root = _kb_require(args)
    actor = _kb_actor(args)
    with yotta_kb.KbLock(root):
        stats = yotta_kb_index.rebuild_all(root)
        yotta_kb.audit(root, actor, "kb.index.rebuild", str(root), "ok",
                       {"entries": stats["total_entries"], "terms": stats["terms"]})
    print("索引已重建：%d 条条目 / %d 个词条" % (stats["total_entries"], stats["terms"]))
    return 0


def _kb_index_status(args):
    root = _kb_require(args)
    status = yotta_kb_index.index_status(root)
    if args.json:
        _kb_out_json(status)
        return 0
    for item in status["categories"]:
        flag = "漂移" if item["drift"] else "一致"
        print("%-24s %-6s 条目 %-4d 构建于 %s"
              % (item["slug"], flag, item["entries"], item["built_at"] or "-"))
    print("全局词表: %s" % ("漂移" if status["global_drift"] else "一致"))
    print("总体: %s" % ("漂移（运行 kb index rebuild）" if status["drift"] else "健康"))
    return 0


def _kb_stats(args):
    root = _kb_require(args)
    data = yotta_kb_index.stats(root)
    if args.json:
        _kb_out_json(data)
        return 0
    print("知识库统计（%s）" % data["root"])
    print("  分类: %d / 条目: %d / 回收站: %d" % (data["categories"], data["total"], data["trash"]))
    print("  状态: %s" % ", ".join("%s=%d" % (k, v) for k, v in sorted(data["by_status"].items())))
    for slug, meta in sorted(data["by_category"].items()):
        print("  %-24s %-16s %d 条%s"
              % (slug, meta["name"], meta["entries"],
                 "" if meta["status"] == "active" else " [%s]" % meta["status"]))
    print("  索引: %s" % ("漂移（运行 kb index rebuild）" if data["index_drift"] else "健康"))
    return 0


def _kb_doctor(args):
    root = _kb_require(args)
    report = yotta_kb.doctor(root, backup_dir=args.backup_dir)
    if args.json:
        _kb_out_json(report)
    else:
        for check in report["checks"]:
            print("[%s] %s%s" % (check["status"], check["name"],
                                 ("：%s" % check["detail"]) if check["detail"] else ""))
        print("doctor: 错误 %d / 警告 %d" % (report["errors"], report["warnings"]))
    return 0 if report["errors"] == 0 else 1


def _kb_backup_create(args):
    root = _kb_require(args)
    actor = _kb_actor(args)
    dest, manifest = yotta_kb.backup_create(root, args.out, actor)
    print("已创建备份：%s" % dest)
    print("  条目 %d / 文件 %d" % (manifest["entries"], len(manifest["files"])))
    return 0


def _kb_backup_list(args):
    items = yotta_kb.backup_list(args.out)
    if args.json:
        _kb_out_json(items)
        return 0
    if not items:
        print("（无备份）：%s" % args.out)
        return 0
    for item in items:
        print("%-40s %-22s 条目 %-5d 文件 %d"
              % (item["name"], item["created"], item["entries"], item["files"]))
    print("共 %d 份" % len(items))
    return 0


def _kb_backup_restore(args):
    actor = _kb_actor(args)
    target = yotta_kb.backup_restore(args.out, args.name, args.into, actor,
                                     force=args.force)
    print("已恢复备份 %s -> %s" % (args.name, target))
    return 0


def _kb_trash_list(args):
    root = _kb_require(args)
    items = yotta_kb.list_trash(root)
    if args.json:
        _kb_out_json(items)
        return 0
    if not items:
        print("（回收站为空）")
        return 0
    for item in items:
        print("%-56s %.1f 天" % (item["name"], item["age_days"]))
    print("共 %d 项（保留 %d 天）" % (len(items), yotta_kb.TRASH_RETENTION_DAYS))
    return 0


def _kb_trash_purge(args):
    root = _kb_require(args)
    actor = _kb_actor(args)
    result = yotta_kb.purge_trash(root, actor, days=args.days, purge_all=args.all)
    print("回收站清理：删除 %d / 保留 %d" % (result["removed"], result["kept"]))
    return 0


def _kb_snapshot_list(args):
    root = _kb_require(args)
    items = yotta_kb.list_snapshots(root)
    if args.json:
        _kb_out_json(items)
        return 0
    if not items:
        print("（暂无快照）")
        return 0
    for item in items:
        print("%-44s %-22s %-16s %d 文件"
              % (item["name"], item["created"], item["op"], item["files"]))
    print("共 %d 个（保留最近 %d 个）" % (len(items), yotta_kb.SNAPSHOT_KEEP))
    return 0


def _kb_snapshot_restore(args):
    root = _kb_require(args)
    actor = _kb_actor(args)
    name = yotta_kb.restore_snapshot(root, args.name, actor)
    print("已恢复快照 %s（恢复前状态已自动快照）" % name)
    return 0


KB_COMMANDS = {
    "init": _kb_init,
    "config_set": _kb_config_set,
    "config_get": _kb_config_get,
    "config_clear": _kb_config_clear,
    "category_create": _kb_category_create,
    "category_list": _kb_category_list,
    "category_rename": _kb_category_rename,
    "category_merge": _kb_category_merge,
    "category_deprecate": _kb_category_deprecate,
    "add": _kb_add,
    "list": _kb_list,
    "show": _kb_show,
    "update": _kb_update,
    "deprecate": _kb_deprecate,
    "review": _kb_review,
    "query": _kb_query,
    "index_rebuild": _kb_index_rebuild,
    "index_status": _kb_index_status,
    "stats": _kb_stats,
    "doctor": _kb_doctor,
    "backup_create": _kb_backup_create,
    "backup_list": _kb_backup_list,
    "backup_restore": _kb_backup_restore,
    "trash_list": _kb_trash_list,
    "trash_purge": _kb_trash_purge,
    "snapshot_list": _kb_snapshot_list,
    "snapshot_restore": _kb_snapshot_restore,
}


def cmd_kb(args):
    name = args.kb_command
    nested = {
        "config": "kb_config_command",
        "category": "kb_category_command",
        "index": "kb_index_command",
        "backup": "kb_backup_command",
        "trash": "kb_trash_command",
        "snapshot": "kb_snapshot_command",
    }
    if name in nested:
        name = "%s_%s" % (name, getattr(args, nested[name]))
    handler = KB_COMMANDS.get(name)
    if handler is None:
        print("[ERROR] 未知 kb 子命令: %s" % name, file=sys.stderr)
        return 4
    return handler(args)


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

    p_update = sub.add_parser("update", help="更新条目状态 / 优先级 / 处置说明")
    p_update.add_argument("id")
    p_update.add_argument("--status", choices=STATUSES)
    p_update.add_argument("--priority", choices=PRIORITIES)
    p_update.add_argument("--note", help="处置说明（追加到 Resolution）")
    p_update.add_argument("--dir")

    p_resolve = sub.add_parser("resolve", help="标记条目已解决（= update --status resolved）")
    p_resolve.add_argument("id")
    p_resolve.add_argument("--note", help="处置说明（追加到 Resolution）")
    p_resolve.add_argument("--dir")

    p_kb = sub.add_parser("kb", help="知识库（分类 / 条目 / 索引 / 查询 / 审核）")
    kb_sub = p_kb.add_subparsers(dest="kb_command", required=True)

    def kb_dir(p):
        p.add_argument("--dir", help="知识库根目录（优先级: --dir > YOTTA_LEARN_KB > 配置 > 默认）")

    def kb_agent(p):
        p.add_argument("--agent", help="写入身份（默认环境变量 YOTTA_LEARN_AGENT）")

    p = kb_sub.add_parser("init", help="初始化知识库（已存在拒绝覆盖）")
    kb_dir(p)
    kb_agent(p)

    p = kb_sub.add_parser("config", help="知识库位置配置")
    cfg_sub = p.add_subparsers(dest="kb_config_command", required=True)
    p2 = cfg_sub.add_parser("set", help="持久化 KB 根目录（任意位置）")
    p2.add_argument("--dir", dest="path", required=True, metavar="PATH")
    cfg_sub.add_parser("get", help="显示解析结果与来源")
    cfg_sub.add_parser("clear", help="清除持久化配置")

    p = kb_sub.add_parser("category", help="分类注册表")
    cat_sub = p.add_subparsers(dest="kb_category_command", required=True)
    p2 = cat_sub.add_parser("create", help="创建分类")
    p2.add_argument("slug")
    p2.add_argument("--name", required=True)
    p2.add_argument("--description", required=True)
    p2.add_argument("--alias", action="append", help="别名（可重复）")
    kb_dir(p2)
    kb_agent(p2)
    p2 = cat_sub.add_parser("list", help="列出分类")
    p2.add_argument("--json", action="store_true")
    kb_dir(p2)
    p2 = cat_sub.add_parser("rename", help="重命名分类（显示名）")
    p2.add_argument("slug")
    p2.add_argument("--name", required=True)
    kb_dir(p2)
    kb_agent(p2)
    p2 = cat_sub.add_parser("merge", help="合并分类（迁移条目 + 留别名）")
    p2.add_argument("slug")
    p2.add_argument("--into", required=True)
    kb_dir(p2)
    kb_agent(p2)
    p2 = cat_sub.add_parser("deprecate", help="停用分类（空分类或 --force）")
    p2.add_argument("slug")
    p2.add_argument("--reason", default="")
    p2.add_argument("--force", action="store_true")
    kb_dir(p2)
    kb_agent(p2)

    p = kb_sub.add_parser("add", help="写入知识条目（默认草稿）")
    p.add_argument("--category", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--message", required=True)
    p.add_argument("--tags", action="append", help="标签（逗号分隔，可重复）")
    p.add_argument("--source", required=True, help="出处（URL / 文件 / 会话）")
    p.add_argument("--evidence", default="")
    p.add_argument("--confidence", choices=list(yotta_kb.CONFIDENCES), default="medium")
    p.add_argument("--json", action="store_true")
    kb_dir(p)
    kb_agent(p)

    p = kb_sub.add_parser("list", help="列出条目（管理视图）")
    p.add_argument("--category")
    p.add_argument("--status", choices=list(yotta_kb.ENTRY_STATUSES))
    p.add_argument("--tag", action="append")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--json", action="store_true")
    kb_dir(p)

    p = kb_sub.add_parser("show", help="查看条目全文")
    p.add_argument("id")
    p.add_argument("--json", action="store_true")
    kb_dir(p)

    p = kb_sub.add_parser("update", help="更新条目字段")
    p.add_argument("id")
    p.add_argument("--title")
    p.add_argument("--message")
    p.add_argument("--tags", action="append")
    p.add_argument("--source")
    p.add_argument("--evidence")
    p.add_argument("--confidence", choices=list(yotta_kb.CONFIDENCES))
    kb_dir(p)
    kb_agent(p)

    p = kb_sub.add_parser("deprecate", help="停用条目（保留可查）")
    p.add_argument("id")
    p.add_argument("--reason", required=True)
    kb_dir(p)
    kb_agent(p)

    p = kb_sub.add_parser("review", help="审核门（三问清单 / --pass / --reject）")
    p.add_argument("id")
    review_group = p.add_mutually_exclusive_group()
    review_group.add_argument("--pass", dest="pass_", action="store_true")
    review_group.add_argument("--reject", action="store_true")
    p.add_argument("--note", default="")
    p.add_argument("--evidence", default="")
    p.add_argument("--force", action="store_true")
    kb_dir(p)
    kb_agent(p)

    p = kb_sub.add_parser("query", help="关键词查询（默认只出已核验）")
    p.add_argument("keywords", nargs="+")
    p.add_argument("--category")
    p.add_argument("--status", help="状态过滤（逗号分隔；默认 verified）")
    p.add_argument("--tag", action="append")
    p.add_argument("--limit", type=int, default=10, help="返回条数（0 = 不限）")
    p.add_argument("--include-draft", action="store_true")
    p.add_argument("--include-deprecated", action="store_true")
    p.add_argument("--json", action="store_true")
    kb_dir(p)

    p = kb_sub.add_parser("index", help="索引管理")
    idx_sub = p.add_subparsers(dest="kb_index_command", required=True)
    p2 = idx_sub.add_parser("rebuild", help="全量重建索引")
    kb_dir(p2)
    kb_agent(p2)
    p2 = idx_sub.add_parser("status", help="索引健康状态")
    p2.add_argument("--json", action="store_true")
    kb_dir(p2)

    p = kb_sub.add_parser("stats", help="统计")
    p.add_argument("--json", action="store_true")
    kb_dir(p)

    p = kb_sub.add_parser("doctor", help="体检")
    p.add_argument("--json", action="store_true")
    p.add_argument("--backup-dir", dest="backup_dir")
    kb_dir(p)

    p = kb_sub.add_parser("backup", help="备份（独立目标目录）")
    bk_sub = p.add_subparsers(dest="kb_backup_command", required=True)
    p2 = bk_sub.add_parser("create", help="创建备份")
    p2.add_argument("--out", required=True)
    kb_dir(p2)
    kb_agent(p2)
    p2 = bk_sub.add_parser("list", help="列出备份")
    p2.add_argument("--out", required=True)
    p2.add_argument("--json", action="store_true")
    p2 = bk_sub.add_parser("restore", help="从备份恢复（目标非空需 --force）")
    p2.add_argument("name")
    p2.add_argument("--out", required=True)
    p2.add_argument("--into", required=True)
    p2.add_argument("--force", action="store_true")
    kb_agent(p2)

    p = kb_sub.add_parser("trash", help="回收站")
    tr_sub = p.add_subparsers(dest="kb_trash_command", required=True)
    p2 = tr_sub.add_parser("list", help="列出回收站")
    p2.add_argument("--json", action="store_true")
    kb_dir(p2)
    p2 = tr_sub.add_parser("purge", help="清理过期回收站（默认 7 天）")
    p2.add_argument("--days", type=int, default=yotta_kb.TRASH_RETENTION_DAYS)
    p2.add_argument("--all", action="store_true")
    kb_dir(p2)
    kb_agent(p2)

    p = kb_sub.add_parser("snapshot", help="快照（破坏性操作前自动创建）")
    sn_sub = p.add_subparsers(dest="kb_snapshot_command", required=True)
    p2 = sn_sub.add_parser("list", help="列出快照")
    p2.add_argument("--json", action="store_true")
    kb_dir(p2)
    p2 = sn_sub.add_parser("restore", help="恢复快照")
    p2.add_argument("name")
    kb_dir(p2)
    kb_agent(p2)

    return ap


COMMANDS = {
    "init": cmd_init,
    "log": cmd_log,
    "update": cmd_update,
    "resolve": cmd_resolve,
    "list": cmd_list,
    "promote": cmd_promote,
    "review": cmd_review,
    "stats": cmd_stats,
    "extract": cmd_extract,
    "kb": cmd_kb,
}


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    cmd = COMMANDS.get(args.command)
    if cmd is None:
        ap.error("未知命令: %s" % args.command)
    try:
        return cmd(args)
    except yotta_kb.KbError as e:
        print("[ERROR] %s" % e.message, file=sys.stderr)
        return e.code
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

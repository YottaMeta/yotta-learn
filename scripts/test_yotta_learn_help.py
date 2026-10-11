#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LEARN_HELP_MODEL 覆盖门禁：与 build_parser() 双向对账。

正例 = 全量对账（44 命令路径 / 全部选项一一对应且说明非空）；
反例 = 缺说明 / 幽灵条目必须被同一校验算法判失败（防止门禁本身失效）。
"""
import argparse
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yotta_learn  # noqa: E402


def walk_parser(parser, prefix=""):
    result = {}
    if prefix:
        result[prefix] = parser
    for name, sub in yotta_learn.cli_subparser_choices(parser).items():
        cmd = (prefix + " " + name).strip()
        result.update(walk_parser(sub, cmd))
    return result


def walk_model(model):
    result = {}

    def rec(commands, prefix):
        for cmd in commands:
            path = (prefix + " " + cmd["name"]).strip()
            result[path] = cmd
            rec(cmd.get("subcommands", []), path)

    for group in model:
        rec(group["commands"], "")
    return result


def parser_flags(parser):
    flags = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            continue
        if isinstance(action, argparse._HelpAction):
            continue
        flags.update(action.option_strings)
    return flags


def validate(parser_map, model_map):
    failures = []
    missing = sorted(set(parser_map) - set(model_map))
    ghost = sorted(set(model_map) - set(parser_map))
    if missing:
        failures.append("模型缺命令路径: " + ", ".join(missing))
    if ghost:
        failures.append("模型含 parser 不存在的条目: " + ", ".join(ghost))

    for path, entry in sorted(model_map.items()):
        if not str(entry.get("usage", "")).startswith(entry.get("name", "")):
            failures.append("usage 未以条目名开头: " + path)
        if not str(entry.get("what", "")).strip():
            failures.append("缺 what: " + path)
        if not str(entry.get("when", "")).strip():
            failures.append("缺 when: " + path)

    for path in sorted(set(parser_map) & set(model_map)):
        want = parser_flags(parser_map[path])
        got = {o["flag"] for o in model_map[path].get("options", [])}
        if want != got:
            failures.append("选项不一致 %s: parser=%s model=%s"
                            % (path, sorted(want), sorted(got)))
        for opt in model_map[path].get("options", []):
            if not str(opt.get("what", "")).strip():
                failures.append("选项缺 what: %s %s" % (path, opt["flag"]))
            if not str(opt.get("when", "")).strip():
                failures.append("选项缺 when: %s %s" % (path, opt["flag"]))
    return failures


def main():
    parser_map = walk_parser(yotta_learn.build_parser())
    model_map = walk_model(yotta_learn.LEARN_HELP_MODEL)
    failures = validate(parser_map, model_map)

    if len(model_map) != 44:
        failures.append("命令路径数应为 44，实际 %d" % len(model_map))

    # 反例自检：门禁必须能抓住「缺说明」与「幽灵条目」两类漂移。
    broken = copy.deepcopy(yotta_learn.LEARN_HELP_MODEL)
    broken[0]["commands"][0]["options"][0]["what"] = ""
    if not validate(parser_map, walk_model(broken)):
        failures.append("反例自检失败：缺说明未被检出")
    ghost_model = copy.deepcopy(yotta_learn.LEARN_HELP_MODEL)
    ghost_model.append({"group": "幽灵", "commands": [
        {"name": "ghost-cmd", "usage": "ghost-cmd", "what": "x", "when": "x", "options": []}]})
    if not validate(parser_map, walk_model(ghost_model)):
        failures.append("反例自检失败：幽灵条目未被检出")

    if failures:
        print("FAIL: LEARN_HELP_MODEL 覆盖门禁")
        for item in failures:
            print("  - " + item)
        return 1
    print("OK: LEARN_HELP_MODEL 覆盖门禁全绿（%d 命令路径；双向对账 + 选项逐条说明 + 反例自检）"
          % len(model_map))
    return 0


if __name__ == "__main__":
    sys.exit(main())

---
name: yotta-learn
version: 0.4.0
description: 元习 —— 跨智能体的学习闭环 + 知识库技能：把错误、纠正与洞见沉淀为 .learnings/ 条目，把验证过的知识存入分类索引的知识库（关键词查询），并提供 MCP stdio 接口与本地图形化管理台（view）。触发：命令失败、用户纠正、发现更好的做法、请求缺失能力、外部接口故障、知识过时、需要沉淀或查询知识时；或用户说 记一笔/学习/沉淀/知识库/kb/查知识/self-improvement/learnings 等。边界：不写入私密/敏感信息（除非用户明确要求）；不自动改动系统文件。
license: MIT
---

# 元习（yotta-learn）

把「这次学到的」变成「下次可复用的」：记录错误、纠正与洞见，供后续会话与技能改进复用。

- **沉淀**：log 命令把条目写入 .learnings/（LEARNINGS / ERRORS / FEATURE_REQUESTS），自动编号 + 时间戳。
- **闭环**：update / resolve 更新条目状态与处置；list / review / stats 回看与统计；promote 提升到 AGENTS.md / CLAUDE.md；extract 生成技能骨架；Pattern-Key 追踪复发模式。
- **知识库（KB）**：kb 命令组把验证过的知识沉淀为分类条目 —— 分类注册、草稿 / 核验、分片索引、关键词查询、审计、回收站、快照与备份；任何智能体经 CLI 读写。
- **联动**：log --remember 可选同步到 yotta-memory（元忆），未安装/失败自动降级，绝不阻断本地记录。

零依赖（Python 3.8+ 标准库），Windows + Linux 通用。

## 何时使用

- 命令或操作意外失败；
- 用户纠正了你（"不对，应该这样…"）；
- 发现了更好的做法 / 知识已过时；
- 用户请求了尚不存在的能力；
- 解决了一个不显然的问题，值得沉淀；
- 开始重要任务前，先 review 待处理条目。
- 想把一条验证过的经验 / 知识沉淀给其他会话或其他智能体复用；
- 需要按关键词查询已有知识（如「发布流程」「SQLite 检索」）。

**Do NOT trigger**：不记录私密信息（令牌、密钥、环境变量值、完整源码）除非用户明确要求；推荐用摘要或脱敏片段。知识库只存知识不存私密：审核门会扫描密钥 / 个人信息 / 本机路径并阻断。

`--category` 是固定枚举：`correction` / `insight` / `knowledge_gap` / `best_practice` / `error` / `other`。
不确定时用 `other`；非法值会退出码 4 并列出全部可用值。

## 快速使用

```bash
# 初始化 .learnings/（幂等，不覆盖已有文件）
python3 scripts/yotta_learn.py init

# 记录一条学习（自动生成 ID 如 LRN-20260826-001）
python3 scripts/yotta_learn.py log --type learning --category correction \\
  --priority high --area git --pattern-key push-gate \\
  --message "推送前必须先跑测试并核对输出"

# 记录一条错误（第二行起进入 Details）
python3 scripts/yotta_learn.py log --type error --priority critical \\
  --message "第一行是摘要"$'\n'"第二行是详情"

# 列出 / 回看 / 统计
python3 scripts/yotta_learn.py list --status pending
python3 scripts/yotta_learn.py review
python3 scripts/yotta_learn.py stats

# 提升到 AGENTS.md / CLAUDE.md（自动去重）
python3 scripts/yotta_learn.py promote LRN-20260826-001

# 闭环：更新状态 / 处置说明（resolve = update --status resolved）
python3 scripts/yotta_learn.py update LRN-20260826-001 --status in_progress --note "处理中"
python3 scripts/yotta_learn.py resolve LRN-20260826-001 --note "已修复并回归"

# 由条目生成技能骨架
python3 scripts/yotta_learn.py extract LRN-20260826-001 --slug my-skill --dry-run

# 可选：同步到元忆（yotta-memory），未安装自动降级
python3 scripts/yotta_learn.py log --message "..." --remember

# 知识库：初始化 → 分类 → 写入草稿 → 核验 → 查询
python3 scripts/yotta_learn.py kb init
python3 scripts/yotta_learn.py kb category create agent-skills \
  --name "智能体与技能开发" --description "技能开发与编排相关知识与方法"
python3 scripts/yotta_learn.py kb add --category agent-skills \
  --title "SQLite FTS5 中文检索的坑" \
  --message "默认分词对中文不友好，需要 bigram 或外部分词器。" \
  --tags "sqlite,检索" --source "experiment"
python3 scripts/yotta_learn.py kb review KB-20261005-001 --pass --evidence "本地实测通过"
python3 scripts/yotta_learn.py kb query 中文检索

# 升库：把 .learnings 条目转成 KB 草稿（保留来源引用，仍走审核门）
python3 scripts/yotta_learn.py kb add --from-learning LRN-20260826-001 \
  --category agent-skills

# 本地图形化管理台（仅 127.0.0.1；页面内嵌会话令牌）
python3 scripts/yotta_learn.py view --port 8791
```

## 数据协议（.learnings/）

- 目录：项目根 .learnings/（可用 --dir 指定）。
- 文件：LEARNINGS.md（LRN-）、ERRORS.md（ERR-）、FEATURE_REQUESTS.md（FEAT-）。
- ID：LRN/ERR/FEAT-YYYYMMDD-XXX（同一天自增）。
- 字段：Logged / Priority / Status / Area / Pattern-Key；正文分 Summary 与 Details。
- 兼容：已有用户数据保留，初始化绝不覆盖；旧格式条目可读。

## 知识库（KB v1）

- 位置：默认 `~/.yottalearn/knowledge`（配置 `~/.yottalearn/config.json`）；优先级 `--dir` > `YOTTA_LEARN_KB` > 配置 > 默认。旧版位置（`~/.yottaskills/yotta-learn.json` / `~/.yottaskills/knowledge`）只读兼容并引导一次性迁移。
- 迁移：`kb config set --dir <新位置> --move`（复制 → doctor + 内容摘要双校验 → 切配置 → 旧库移出原位）；不带 `--move` 只切指针并明确提示「旧库未迁移」，可用 `--move --from <旧库>` 补迁。
- 结构：`categories/<slug>/`（category.json + entries/ + index.json）+ `index/`（全局词表 / 统计）+ `audit/` + `.trash/` + `snapshots/`。
- 条目：Markdown + 受控 frontmatter（单行键值；字符串单引号；数组 JSON）；ID `KB-YYYYMMDD-XXX`。
- 状态机：draft（默认）→ verified（review --pass 需证据）→ deprecated；reject 入回收站（保留 7 天）。
- 查询：中文 bigram + 单字兜底；默认只出 verified；索引漂移自动降级线性扫描。
- 升库：`kb add --from-learning <LRN-ID>` 把 .learnings 条目转成 KB 草稿（保留可移植来源引用，仍走审核门）。
- AI 接口（MCP）：`scripts/yotta_learn_mcp.py`（stdio；读 kb_query/kb_get/kb_list/kb_stats/kb_categories，写 kb_add/kb_review/kb_update/kb_deprecate/kb_category_create，运维 kb_doctor/kb_index_rebuild；写工具 fail-closed）。
  AI 自动接入：首次使用时由 AI 把该 server 写入客户端 `mcpServers` 并写永久记忆护栏；未加载自动降级 CLI。配置示例：
  ```json
  {"mcpServers":{"yotta-learn":{"command":"python","args":["<技能目录>/scripts/yotta_learn_mcp.py"]}}}
  ```
- 图形化管理台：`yotta-learn view`（默认 `127.0.0.1:8791`；本机会话令牌 + 破坏性确认串 + 审计；七视图：总览 / 分类 / 条目 / 搜索 / 审核 / 位置 / 运维）。
- 完整命令面、协议与可靠性说明：references/kb.md。

## 元忆联动（可选）

- 显式开启：log --remember。
- 运行时探测元忆：未安装 → A；已安装未初始化 → B；失败/超时 → C。
- 降级 A/B/C 只提示，绝不阻断本地 .learnings/ 记录。
- 不写入 package.json 依赖。

## Hook 模板

见 hooks/ 目录：Claude Code（claude-settings.json）、Codex（codex-settings.json）、
OpenClaw（openclaw-setup.md）；activator.sh / error-detector.sh 为 Linux-only 的可选 bash hook。

## 参考

- references/examples.md — 记录示例与字段说明
- references/kb.md — 知识库完整命令面、数据协议与可靠性说明
- references/hooks-setup.md — 各智能体 hook 接入详细步骤
- references/walkthroughs.md — 命令失败 / 用户纠正 / 接口降级三类复杂走查
- references/faq.md — 常见问题速查与安装排障

## 常见问题（速查）

条目写哪、重复问题、私密信息、知识库位置 / 审核门、元忆联动失败、hook 不生效时，先看 references/faq.md。

---
name: yotta-learn
version: 0.1.2
description: 元习 —— 跨智能体的学习闭环技能：把错误、纠正与洞见沉淀为 .learnings/ 条目，供后续会话与技能改进复用。触发：命令失败、用户纠正、发现更好的做法、请求缺失能力、外部接口故障、知识过时、需要沉淀经验时；或用户说 记一笔/学习/沉淀/self-improvement/learnings 等。边界：不写入私密/敏感信息（除非用户明确要求）；不自动改动系统文件。
license: MIT
---

# 元习（yotta-learn）

把「这次学到的」变成「下次可复用的」：记录错误、纠正与洞见，供后续会话与技能改进复用。

- **沉淀**：log 命令把条目写入 .learnings/（LEARNINGS / ERRORS / FEATURE_REQUESTS），自动编号 + 时间戳。
- **复用**：list / review / stats 回看与统计；promote 把重要条目提升到 AGENTS.md / CLAUDE.md。
- **改进**：extract 由高价值条目生成新技能骨架；Pattern-Key 追踪复发模式。
- **联动**：log --remember 可选同步到 yotta-memory（元忆），未安装/失败自动降级，绝不阻断本地记录。

零依赖（Python 3.8+ 标准库），Windows + Linux 通用。

## 何时使用

- 命令或操作意外失败；
- 用户纠正了你（"不对，应该这样…"）；
- 发现了更好的做法 / 知识已过时；
- 用户请求了尚不存在的能力；
- 解决了一个不显然的问题，值得沉淀；
- 开始重要任务前，先 review 待处理条目。

**Do NOT trigger**：不记录私密信息（令牌、密钥、环境变量值、完整源码）除非用户明确要求；推荐用摘要或脱敏片段。

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

# 由条目生成技能骨架
python3 scripts/yotta_learn.py extract LRN-20260826-001 --slug my-skill --dry-run

# 可选：同步到元忆（yotta-memory），未安装自动降级
python3 scripts/yotta_learn.py log --message "..." --remember
```

## 数据协议（.learnings/）

- 目录：项目根 .learnings/（可用 --dir 指定）。
- 文件：LEARNINGS.md（LRN-）、ERRORS.md（ERR-）、FEATURE_REQUESTS.md（FEAT-）。
- ID：LRN/ERR/FEAT-YYYYMMDD-XXX（同一天自增）。
- 字段：Logged / Priority / Status / Area / Pattern-Key；正文分 Summary 与 Details。
- 兼容：已有用户数据保留，初始化绝不覆盖；旧格式条目可读。

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
- references/hooks-setup.md — 各智能体 hook 接入详细步骤

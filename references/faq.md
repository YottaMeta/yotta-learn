# 元习常见问题

## 速查索引

- **记录**：条目写到哪里 · 怎么记错误/多行详情 · 记重了怎么办
- **复用**：怎么回看 · 怎么提升到 AGENTS.md · 怎么生成技能骨架
- **知识库**：和 .learnings 什么关系 · source/evidence 怎么填 · 查不到草稿怎么办 · 放哪 / 怎么备份 · 审核被阻断怎么办
- **安全**：能记私密信息吗 · 元忆联动失败怎么办
- **报错**：退出码 · hook 不生效
- **安装**：装到哪 · 与元忆/元序分工

---

## 1. `.learnings/` 会写到哪里？

默认写到运行目录下的 `.learnings/`；重要项目可用 `--dir <路径>` 指定。`init` 幂等，不会覆盖已有文件。

## 2. 怎么记一条错误并带详情？

`log --type error --priority critical --message "第一行是摘要"`，需要详情时把第二行起放进消息中；支持换行分隔，列表/回看会保留摘要与详情两部分。

## 3. 重复问题会反复记吗？

建议同一类问题用同一个 `--pattern-key`（如 `push-gate`、`powerShell-quoting`）。`list`/`stats` 可以按 pattern 聚合；`promote` 到 AGENTS.md/CLAUDE.md 时会自动去重。

## 4. 能记录密钥/私密信息吗？

默认不能：私钥、令牌、环境变量值、完整凭据、完整源码除非用户明确要求，否则不记录；应写摘要或脱敏片段。

## 5. `log --remember` 与元忆联动失败会阻断吗？

不会。未安装、未初始化、超时都会降级为提示 A/B/C，本地 `.learnings/` 记录不受影响；这是设计好的降级路径，不是错误。

## 6. 怎么把经验提升为长期规则？

`promote <ID>` 会把条目内容写入 AGENTS.md / CLAUDE.md 的 Learnings 节（自动去重）；需要沉淀成新技能骨架时用 `extract <ID> --slug my-skill --dry-run` 先预览。

## 7. Hook 为什么没自动触发？

确认按 hooks/ 下对应平台配置放置（Claude Code 的 claude-settings.json、Codex 的 codex-settings.json 等）；命令行调用元习不需要 hook，hook 只是帮你自动捕获失败场景。bash hook 仅 Linux 可用。

## 8. 退出码是什么意思？

0 = 成功；1 = 未找到；4 = 用法或校验错误（缺少参数、分类不存在等）；5 = 门禁阻断（敏感命中 / 疑似重复）；6 = 完整性（拒绝覆盖 / 数据损坏 / 写锁超时）。所有失败都会给出明确报错并建议修复，不会静默退出。

## 9. 怎么开始重要任务前先复习？

`review` 会列出待处理条目；`list --status pending --area git` 可按状态/领域过滤。开工前先看是否有同类教训或待提升规则。

## 10. 安装不上/没自动加载怎么办？

用 `npx -y @yottameta/yotta-learn --agent <名称>` 或 `--dir <技能目录>`；npm 镜像传播延迟时临时加 `--registry=https://registry.npmjs.org/`。装到当前项目后，新会话读取技能目录才会生效。

## 11. 元习和元忆怎么分工？

元习是“项目内轻量学习闭环”，记录条目、复用、提升到规则文件；元忆是跨会话/跨项目记忆库。元习的 `--remember` 可以把高价值条目同步给元忆，但两者都保留独立数据。

## 12. 条目要不要写完整错误输出？

不要。建议写“摘要 + 根因 + 修复步骤”，错误堆栈只保留关键一行或已脱敏片段；完整输出往往包含路径、账号、密钥等隐私，不利于长期复用。

## 13. 知识库和 `.learnings/` 是什么关系？

`.learnings/` 负责采集与闭环：记录错误 / 纠正 / 洞见，更新状态、提升规则；知识库负责沉淀与检索：把验证过的知识按分类存放、供关键词查询。建议流程：`.learnings/` 里验证过的经验 → `kb add` 写入知识库 → `kb review --pass --evidence "..."` 核验入库。

## 14. `kb add` 的 source / evidence 怎么填？

`--source` 必填，写出处（URL / 文件 / 实验 / 会话）；`--evidence` 可以后补，核验通过（`kb review --pass`）时必须提供 —— 写入时给出，或核验时用 `--evidence` 补。

## 15. 查询为什么查不到刚写入的条目？

新条目默认是草稿（draft），查询默认只出已核验（verified）。先 `kb review <ID> --pass --evidence "..."`，或在查询时加 `--include-draft` 显式包含草稿。

## 16. 知识库放在哪？怎么换位置 / 备份？

默认 `~/.yottaskills/knowledge`；用 `kb config set --dir <路径>` 可指定任意位置（优先级 `--dir` > `YOTTA_LEARN_KB` > 配置 > 默认）。备份用 `kb backup create --out <目录>`，恢复用 `kb backup restore <名称> --out <目录> --into <目标>`；日常体检用 `kb doctor`（可加 `--backup-dir`）。

## 17. 审核被阻断（敏感 / 重复）怎么办？

敏感命中：确认样例已脱敏后，用 `--force --note '说明'` 放行（留审计）；疑似重复：先 `kb show` 对比，确认不重复后用 `--force` 放行，或对重复条目执行 `kb deprecate` / `kb review --reject`。

## 13. `--category` 可以填哪些值？

固定枚举：`correction` / `insight` / `knowledge_gap` / `best_practice` / `error` / `other`。填错会退出码 4，并在错误信息里列出全部可用值；不确定时用 `other`。

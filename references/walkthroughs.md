# 元习复杂场景走查

## 走查 1：命令失败后的“踩坑 → 修复 → 沉淀”

场景：PowerShell 里一条含反引号的 node 命令执行失败，根因是外层引号把反引号吃掉。

1. AI 复述失败现场：命令、报错、根因。
2. 用 `log --type error --priority high --area shell --pattern-key quoting --message "反引号/中文长参数先写临时脚本，别内联"` 落一条 ERR。
3. 若修复方法值得跨会话复用，`promote <ID>` 写入 AGENTS.md/CLAUDE.md。
4. 下次同 pattern 出现时 `list --pattern-key quoting` 能直接带出旧经验。

## 走查 2：用户纠正后的“事实修正 + 边界”

场景：用户指出“默认不会读 .agents/skills”，此前记录写反了。

1. 记录 `--type learning --priority high --area agent-dirs --pattern-key skills-dirs`，摘要写正确口径。
2. Details 里写一句修正来源（“用户 2026-09-09 纠正”），不写完整私密上下文。
3. 用 `stats` 确认同类条目是否反复出现；若反复，说明需要升级为全局规则而不是单条记忆。
4. `extract <ID> --slug my-skill --dry-run` 预览是否能沉淀成新技能骨架。

## 走查 3：外部接口故障的“降级判断”

场景：调用元忆超时，但本地记录不能断。

1. `log --remember` 遇到探测超时降级 C，只提示、不阻断。
2. 先在 .learnings/ 记录故障现场与降级路径。
3. 高价值条目再单独对元忆重试同步，避免把“元忆故障”和“学习内容”混在同一层。

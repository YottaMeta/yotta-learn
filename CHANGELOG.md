# 更新日志

## v0.4.0 (2026-10-07)

- 存储独立与迁移：配置与默认库迁到 `~/.yottalearn/`（`config.json` + `knowledge/`）；旧位置（`~/.yottaskills/yotta-learn.json` / `~/.yottaskills/knowledge`）只读兼容（回退生效时写操作 fail-closed + 一次性迁移引导，读操作与迁移不受影响）；`kb config set --dir <路径> --move [--from <源库>]`（复制 → doctor + 内容摘要双校验 → 切配置 → 旧库移出原位，fail-closed）；不带 `--move` 时明确提示「旧库未迁移」；`kb config get` 显示来源 / 未迁移块 / 最近迁移块。
- MCP stdio server（`scripts/yotta_learn_mcp.py`）：12 工具（读 5 / 写 5 / 运维 2），双时代协议（2026-07-28 无状态 + 2025-11-25 握手）；写工具与 CLI 同源 fail-closed（草稿 / 审核门 / 敏感阻断 / force 需 note）。
- 本地管理台（`yotta-learn view` + `assets/view.html`）：仅绑定 127.0.0.1；七视图（总览 / 分类 / 条目 / 搜索 / 审核 / 位置 / 运维）；会话令牌 + 破坏性确认串 + 审计；严格 CSP / 零远程资源。
- 升库：`kb add --from-learning <LRN-ID>` 把 .learnings 条目转成 KB 草稿（保留可移植来源引用，仍走审核门）。
- 修复：位置迁移后审计写回旧根（重建旧目录）→ 审计改写新库。
- 修复：旧版位置回退生效时写入静默落旧库（与「只读兼容」口径不符）→ 写操作 fail-closed（CLI / MCP / 面板同一写锁门，exit 5 + 迁移指引）；迁移与备份不受影响。
- 测试：新增 `test_yotta_learn_mcp.py`（54 项）与 `test_yotta_learn_view.py`（39 项），扩展 `test_yotta_kb.py`（37 项）；真窗口走查工具 `tools/check_learn_view.js`。
- 文档：SKILL / README（中英）/ FAQ / references/kb.md 全量更新。

## v0.3.0 (2026-10-05)

- 知识库（KB v1）：新增 `kb` 命令组 —— 分类注册（别名 / 合并 / 停用）、条目（草稿 / 核验 / 停用）、受控 frontmatter 协议、中文 bigram + 单字兜底分片索引、关键词查询（默认只出已核验）、审计、回收站（7 天）、快照（破坏性操作前自动）、独立目录备份、doctor 体检。
- 学习闭环补全：新增 `update`（状态 / 优先级 / 处置说明）与 `resolve` 快捷命令；修复多条目文件中提升第 2+ 条时 Promoted-To 写入错块的缺陷。
- 可靠性：原子写 + 跨进程写锁（过期接管）+ init 防覆盖（库已存在拒绝）+ 索引漂移自动降级线性扫描 + `kb index rebuild` / `status`。
- 测试：新增 `scripts/test_yotta_kb.py`（25 项）并扩展 `scripts/test_yotta_learn.py`（20 项）；`npm test` 链更新。
- 文档：SKILL / README（中英）/ FAQ 更新，新增 `references/kb.md` 完整参考。

## v0.2.2 (2026-10-01)

- 安装器卫生批次：`bin/install.js` / `install.sh` 统一（未知参数报错 exit 2、`--help` / `--version`、残留清理白名单、嵌套载荷保留）；由模板单一真源渲染，接入漂移门禁。
- 自带安装器测试（`test/install.test.js`）更新为统一行为断言。

## v0.2.1 (2026-09-17)

- `--category` 固定枚举写入 SKILL、README 与 FAQ：`correction / insight / knowledge_gap / best_practice / error / other`；非法值错误提示列出全部可用项。
- 修正 README 中不存在的 `tooling` 示例，改为合法 `error`；新增枚举回归。

## v0.2.0 (2026-09-09)

- 评测完善批 2：新增 references/faq.md 与 references/walkthroughs.md（命令失败/用户纠正/接口降级三类复杂走查）；SKILL.md 增加 FAQ 速查节。
- 安装器错误处理：用法/目标/安装错误统一退出码与修复建议；新增 test/install.test.js。
- package.json 补 npm test 脚本；版本对齐 0.2.0（package / SKILL / CHANGELOG / CLI）。

## v0.1.4 (2026-08-29)

- 安装方式统一为四方式（对齐发布规范 §3.3.1）：方式一 `npx -y @yottameta/yotta-learn --agent <name>` / `--dir <dir>`（推荐，走 npm 源）；方式二 `git clone https://github.com/YottaMeta/yotta-learn.git`；方式三 GitHub Download ZIP；方式四 `bash install.sh --agent/--dir/--list`。移除 `npx skills` 与 `-g` 推荐；中英双 README 安装节同步。
- 版本对齐：package.json / SKILL.md / CHANGELOG / 引擎 VERSION / 测试断言 / README 锚点 = 0.1.4。
- 无功能变更（仅文档与版本同步）。

## v0.1.3 (2026-08-28)

中英双语文档：README.md（英文主文件，作为 GitHub / npm / ClawHub 主页） + 新增 README.zh-CN.md（中文全档）；安装方式统一为三方式（npx -g / --dir、install.sh、手动复制），移除 npx 固定 --agent codex（--agent 仅 install.sh 使用）；npm description 改英文；package.json files 加入 README.zh-CN.md。无功能变更。
## v0.1.1 (2026-08-26)

README 按标准补全：新增「这是什么 / 核心价值 / 核心优势 / 功能体系 / 数据协议 / 常见问题 / 相关技能 / 升级卸载」等章节，与 YottaMeta 技能矩阵 README 标准对齐；无功能变更。


## v0.1.0 (2026-08-26)

YottaMeta 自有实现首版（参考开源社区 self-improving-agent 类技能思路，全新实现，不包含其代码）：

- CLI 全跨平台：init / log / list / promote / review / stats / extract 七个子命令。
- .learnings/ 协议：LEARNINGS / ERRORS / FEATURE_REQUESTS 三文件，ID 格式 LRN/ERR/FEAT-YYYYMMDD-XXX；
  兼容已有用户数据，初始化绝不覆盖。
- 元忆联动（可选 + 自动降级）：log --remember 显式开启，未安装/未初始化/失败分别降级 A/B/C，
  绝不阻断本地记录；先 search 去重再同步；不写依赖。
- 复发模式追踪：Pattern-Key 聚合，出现 >= 2 次自动提示合并 + 提权。
- 提升（promote）自动去重；extract 由条目生成技能骨架。
- Hook 模板：OpenClaw / Claude Code / Codex 三种配置模板；bash hook 标注 Linux-only。
- 零依赖（Python 3.8+ 标准库），Windows + Linux 通用，UTF-8 加固（GBK 控制台不崩）。
- 版权：YottaMeta 纯自有 MIT + NOTICE 品牌声明；README/NOTICE 一行来源说明。

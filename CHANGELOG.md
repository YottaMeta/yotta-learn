# 更新日志

## v0.1.1 (2026-08-26)

README 按标准补全：新增「这是什么 / 核心价值 / 核心优势 / 功能体系 / 数据协议 / 常见问题 / 相关技能 / 升级卸载」等章节，与 YottaMeta 技能矩阵 README 标准对齐；无功能变更。


## v0.1.0 (2026-08-26)

YottaMeta 自有实现首版（重写自第三方技术包 self-improving-agent v3.0.13，已完全重写，无上游代码）：

- CLI 全跨平台：init / log / list / promote / review / stats / extract 七个子命令。
- .learnings/ 协议：LEARNINGS / ERRORS / FEATURE_REQUESTS 三文件，ID 格式 LRN/ERR/FEAT-YYYYMMDD-XXX；
  兼容已有用户数据，初始化绝不覆盖。
- 元忆联动（可选 + 自动降级）：log --remember 显式开启，未安装/未初始化/失败分别降级 A/B/C，
  绝不阻断本地记录；先 search 去重再同步；不写依赖。
- 复发模式追踪：Pattern-Key 聚合，出现 >= 2 次自动提示合并 + 提权。
- 提升（promote）自动去重；extract 由条目生成技能骨架。
- Hook 模板：OpenClaw / Claude Code / Codex 三种配置模板；bash hook 标注 Linux-only。
- 零依赖（Python 3.8+ 标准库），Windows + Linux 通用，UTF-8 加固（GBK 控制台不崩）。
- 版权：YottaMeta 纯自有 MIT + NOTICE 品牌声明；README 一行上游致谢。

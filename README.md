<p align="center">
  <img src="assets/banner.png" alt="yotta-learn banner" width="100%" />
</p>

# yotta-learn（元习）

跨智能体的学习闭环技能：把错误、纠正与洞见沉淀为 .learnings/ 条目，供后续会话与技能改进复用。

- **零依赖**：Python 3.8+ 标准库，Windows + Linux 通用。
- **不覆盖**：初始化绝不改动已有 .learnings/ 数据。
- **可联动**：可选同步 yotta-memory（元忆），未安装自动降级，不阻断本地记录。
- **可改进**：Pattern-Key 复发追踪 + extract 技能骨架生成。

## 安装

本技能为「技能包」：先装到你的智能体技能目录，再由智能体按需调用其中的 CLI。

### 方式一：npm（推荐，Windows / Linux / macOS）

```bash
npx -y @yottameta/yotta-learn --agent codex      # 装到 Codex
npx -y @yottameta/yotta-learn --agent claude    # 装到 Claude Code
npx -y @yottameta/yotta-learn --agent cursor    # 装到 Cursor
npx -y @yottameta/yotta-learn -g                # 装到全部已知智能体
npx -y @yottameta/yotta-learn --list            # 查看智能体 → 默认目录
```

### 方式二：install.sh（Linux / macOS）

```bash
git clone https://github.com/YottaMeta/yotta-learn.git
cd yotta-learn
bash install.sh --agent codex        # 或 --agent claude / --dir <路径> / -g
```

### 方式三：手动复制

把本仓库内容复制到你的智能体技能目录（Claude Code ~/.claude/skills/、Cursor ~/.cursor/skills/、Codex ~/.codex/skills/ 或 $CODEX_HOME/skills、通用 ~/.agents/skills/）。

## 快速使用

```bash
python3 scripts/yotta_learn.py init
python3 scripts/yotta_learn.py log --type error --priority high --message "接口超时重试导致重复提交"
python3 scripts/yotta_learn.py list --status pending
python3 scripts/yotta_learn.py promote LRN-20260826-001
python3 scripts/yotta_learn.py extract LRN-20260826-001 --slug my-skill --dry-run
```

exit code：0 = 成功；1 = 未找到/无事可做；4 = 用法错误。

## 与 yotta-memory（元忆）的关系

yotta-learn 与 yotta-memory 互补：前者负责「项目内 .learnings/ 学习闭环」，后者负责「跨会话长期记忆」。
log --remember 可把条目同步到元忆；元忆未安装或不可用时自动降级，不影响本地记录。

## 测试

```bash
python3 scripts/test_yotta_learn.py
```

覆盖：全命令冒烟、幂等初始化、去重、复发模式、元忆联动四态（A/B/C/ok）、GBK 控制台加固。

## 许可证与品牌

- MIT License（Copyright © 2026 YottaMeta），详见 LICENSE。
- 品牌声明见 NOTICE：YottaMeta / 元忆 / 元习 / yotta-* 为 YottaMeta 品牌，派生作品须改名并声明无关联。
- 上游来源致谢：协议与设计参考开源社区 self-improving-agent 类技能思路，实现为 YottaMeta 自有。

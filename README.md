<p align="center"><b>Language</b>: English · <a href="./README.zh-CN.md">中文</a></p>

<p align="center">
  <img src="assets/banner.png" alt="yotta-learn banner" width="100%" />
</p>

<h1 align="center">yotta-learn · 元习</h1>

<p align="center">YottaMeta's cross-agent <b>learning-loop</b> skill: turns mistakes, corrections and insights into reusable <b>.learnings/</b> entries for later sessions and skill improvement. Suited for command failures, user corrections, discovering a better practice, requesting a missing capability, external-interface failures, and stale knowledge.</p>
<p align="center">Activates on command failure / user correction / a better approach / a missing capability / an external-interface failure / stale knowledge / a need to capture experience, or when the user says 记一笔 / learn / 沉淀 / self-improvement / learnings — judged by whether experience should be captured, not by keyword luck.</p>
<p align="center">Python 3.8+ standard library, zero dependencies; Windows + Linux; init never overwrites existing .learnings/ data.</p>

<p align="center">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue" /></a>
  <a href="https://agentskills.io/"><img alt="Standard: agentskills.io" src="https://img.shields.io/badge/standard-agentskills.io-orange" /></a>
  <a href="https://www.npmjs.com/package/@yottameta/yotta-learn"><img alt="npm package" src="https://img.shields.io/npm/v/@yottameta/yotta-learn" /></a>
  <a href="https://github.com/YottaMeta/yotta-learn"><img alt="GitHub stars" src="https://img.shields.io/github/stars/YottaMeta/yotta-learn" /></a>
  <a href="https://github.com/YottaMeta/yotta-learn/commits/main"><img alt="last commit" src="https://img.shields.io/github/last-commit/YottaMeta/yotta-learn" /></a>
  <a href="https://github.com/YottaMeta/yotta-learn"><img alt="PRs welcome" src="https://img.shields.io/badge/PRs-welcome-brightgreen" /></a>
</p>

## What it is

The most common waste for an AI agent is repeating the same mistake across sessions. Yuanxi turns "what I learned this time" into "reusable next time": it captures mistakes, corrections and insights as project-local .learnings/ entries for later sessions to review, aggregate and reuse.

It is not tied to one platform — it is an agent-agnostic CLI toolkit: install it into any agent that supports Agent Skills, and it only writes to the .learnings/ directory you specify. No dependency is added to package.json.

## Core value

- **Capture** — the log command writes entries into .learnings/ (LEARNINGS / ERRORS / FEATURE_REQUESTS), auto-numbered and timestamped.
- **Reuse** — list / review / stats to review and aggregate; promote lifts important entries into AGENTS.md / CLAUDE.md.
- **Improve** — extract builds a new skill skeleton from high-value entries; Pattern-Key tracks recurring patterns.
- **Optional integration** — log --remember optionally syncs to yotta-memory; degrades gracefully when not installed / failed, and never blocks local capture.
- **No overwrite** — init never touches existing .learnings/ data; old-format entries remain readable.

## Advantages

| Advantage | Description |
|---|---|
| **Cross-agent** | .learnings/ is a project-local file; Claude Code / Codex / Cursor etc. share the same copy |
| **Pattern-Key recurrence** | Repeating patterns get flagged, upgrading occasional errors into systemic improvements |
| **Optional integration** | Connects to 元忆 but degrades A/B/C when not installed / uninitialized / failed, never blocks local capture |
| **Idempotent init** | init can be re-run without overwriting existing entries |
| **Auto-dedup** | promote / extract deduplicate automatically |
| **Zero dependency** | Python 3.8+ standard library; no daemon / no database; Windows + Linux |
| **Ecosystem distribution** | GitHub + npm dual-source; npx / install.sh / manual copy |

## Commands

| Command | Purpose |
|---|---|
| init | Initialize .learnings/ (idempotent, never overwrites existing files) |
| log | Record a learning / error / feature request (auto ID like LRN-20260826-001) |
| list / review / stats | Review and aggregate entries |
| promote | Lift important entries into AGENTS.md / CLAUDE.md (auto-dedup) |
| extract | Build a skill skeleton from high-value entries (--dry-run preview) |
| log --remember | Optional sync to yotta-memory; degrades when not installed |

## Data protocol

- Directory: project root .learnings/ (override with --dir).
- Files: LEARNINGS.md (LRN-), ERRORS.md (ERR-), FEATURE_REQUESTS.md (FEAT-).
- ID: `LRN/ERR/FEAT-YYYYMMDD-XXX` (auto-increment per day).
- Fields: Logged / Priority / Status / Area / Pattern-Key; body split into Summary and Details.
- Compatibility: existing user data is preserved; init never overwrites; old-format entries readable.

## Usage

```bash
# Initialize .learnings/ (idempotent, never overwrites existing files)
python3 scripts/yotta_learn.py init

# Record a learning (auto ID like LRN-20260826-001)
python3 scripts/yotta_learn.py log --type learning --category correction \
  --priority high --area git --pattern-key push-gate \
  --message "Run the tests and verify output before pushing"

# Record an error / feature request
python3 scripts/yotta_learn.py log --type error --category tooling --priority medium \
  --area build --pattern-key pyc --message "py_compile created __pycache__ that leaked into npm pack"

# Review and aggregate
python3 scripts/yotta_learn.py list
python3 scripts/yotta_learn.py stats

# Lift an important entry into AGENTS.md / CLAUDE.md (auto-dedup)
python3 scripts/yotta_learn.py promote ERR-20260827-003

# Build a skill skeleton from a high-value entry (preview only)
python3 scripts/yotta_learn.py extract LRN-20260826-001 --slug my-skill --dry-run

# Optional: sync to yotta-memory; degrades when not installed
python3 scripts/yotta_learn.py log --message "..." --remember
```

**Exit-code semantics**: 0 = success; 1 = nothing found / nothing to do; 4 = usage error.

## Installation

Pick any of the three methods; skill files are always fetched from **npm** (GitHub can be slow without a proxy; npm supports mirrors).

### Method 1: npm (recommended, one-liner)
```bash
# Optional China mirror: npm config set registry https://registry.npmmirror.com
npx -y @yottameta/yotta-learn -g
npx -y @yottameta/yotta-learn --dir <your skills dir>   # any agent: install to a custom directory
```
> Agent not in the preset list? Use `--dir` to point at its skills directory, or copy manually (Method 3). `--list` shows the default directory of each agent. To grab the files yourself, run `npm pack @yottameta/yotta-learn` and unpack, then use Method 2 or 3.

### Method 2: install.sh
After obtaining the skill folder (`npm pack` unpack or `git clone`), enter the folder:
```bash
bash install.sh -g    # user-level; bash install.sh --list shows all directories
bash install.sh --agent codex   # a specific agent (see --list)
bash install.sh       # project-level: auto-detect existing skills directories
bash install.sh --dir /path/to/skills
```
> Covers 17 agent families, including Trae / Qwen / Comate / CodeBuddy / Kimi.

### Method 3: manual copy
Copy the whole `yotta-learn` folder into the target agent's skills directory. Common user-level locations (`%USERPROFILE%` on Windows, `~` on Linux/macOS):

| Agent | User-level directory | Project-level directory |
|---|---|---|
| Codex | `%USERPROFILE%\.codex\skills\yotta-learn\` | `.codex\skills\` |
| Claude Code | `%USERPROFILE%\.claude\skills\yotta-learn\` | `.claude\skills\` |
| Cursor | `%USERPROFILE%\.cursor\skills\yotta-learn\` | `.cursor\skills\` |
| Windsurf | `%USERPROFILE%\.codeium\windsurf\skills\yotta-learn\` | `.windsurf\skills\` |
| opencode | `%USERPROFILE%\.config\opencode\skills\yotta-learn\` | `.opencode\skills\` |
| Gemini | `%USERPROFILE%\.gemini\skills\yotta-learn\` | `.gemini\skills\` |
| Goose | `%USERPROFILE%\.config\goose\skills\yotta-learn\` | `.goose\skills\` |
| Amp | `%USERPROFILE%\.config\agents\skills\yotta-learn\` | `.agents\skills\` |
| Kiro | `%USERPROFILE%\.kiro\skills\yotta-learn\` | `.kiro\skills\` |
| WorkBuddy | `%USERPROFILE%\.workbuddy\skills\yotta-learn\` | `.workbuddy\skills\` |
| Trae Code CLI | `%USERPROFILE%\.traecli\skills\yotta-learn\` | `.traecli\skills\` |
| Trae IDE (CN) | `%USERPROFILE%\.trae-cn\skills\yotta-learn\` | `.trae\skills\` |
| Qwen Code | `%USERPROFILE%\.qwen\skills\yotta-learn\` | `.qwen\skills\` |
| Comate | `%USERPROFILE%\.comate\skills\yotta-learn\` | `.comate\skills\` |
| CodeBuddy | `%USERPROFILE%\.codebuddy\skills\yotta-learn\` | `.codebuddy\skills\` |
| Kimi | `%USERPROFILE%\.kimi\skills\yotta-learn\` | `.kimi\skills\` |
| Generic AGENTS.md | `%USERPROFILE%\.agents\skills\yotta-learn\` | `.agents\skills\` |

> If Codex's `CODEX_HOME` is set, it overrides the default; the same applies to opencode's `XDG_CONFIG_HOME`. `.agents\skills` is not a universal directory — only OpenCode / Cursor / Cline / Amp / Kimi / Gemini CLI / GitHub Copilot etc. read it; **Claude Code and Codex do not read it by default**. When unsure, use `--dir` or let the agent install it.

> Project-level: run `npx -y @yottameta/yotta-learn` or `bash install.sh` inside the project to install into the detected project-level directory.

## Upgrade / uninstall

- **Upgrade**: reinstall the latest version — `npx -y @yottameta/yotta-learn -g` or re-run `bash install.sh -g`. Old files in the skill directory are overwritten; other project files are untouched.
- **Uninstall**: delete the `yotta-learn` folder in the target agent's skills directory (see the table above).

## FAQ

- **Will it overwrite my existing entries?** No. init is idempotent and never touches existing .learnings/ data; old-format entries remain readable.
- **Can I use it without 元忆?** Yes. log --remember is optional; it degrades A/B/C when not installed / uninitialized / failed, recording only locally in .learnings/ and never blocking you.
- **Does it record sensitive info?** By default no (tokens, keys, env-var values, full source). If truly needed, use a summary or a redacted snippet.
- **Who is it for?** Any agent workflow that wants to avoid repeating the same mistake — especially multi-agent / multi-session / multi-person collaboration.

## Related skills

Same YottaMeta skill matrix (learning & engineering family): [yotta-memory](https://github.com/YottaMeta/yotta-memory) (元忆, cross-session long-term memory) complements 元习 — one handles "project-local .learnings/ loop", the other "cross-session long-term memory"; [anti-shallow](https://github.com/YottaMeta/anti-shallow) (anti-shallow) and [workflow-standard](https://github.com/YottaMeta/workflow-standard) (workflow standard) reinforce it from the execution-discipline side, so you don't "capture but stay sloppy".

## Development & validation

Run in this repo: `python tools/validate-skill.py yotta-learn`.

## License

MIT © YottaMeta — see [LICENSE](./LICENSE). Brand statement in [NOTICE](./NOTICE). Upstream attribution: protocol & design reference the open-source self-improving-agent family; implementation is YottaMeta's own.

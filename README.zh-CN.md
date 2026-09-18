# agent-handoff

[![tests](https://github.com/AgathonLi/agent-handoff/actions/workflows/test.yml/badge.svg)](https://github.com/AgathonLi/agent-handoff/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**简体中文** · [English](README.md)

宿主中立的会话交接文档，用于跨 agent 开发。

在一个 agent 里写交接，在另一个 agent 里接着干。适用于 Claude Code、Codex、
WorkBuddy、Cursor、OpenCode、Zed，以及任何能读 Markdown、跑 Python 的工具。

## 它解决什么问题

多数交接工具把文档存进某一个客户端的配置命名空间——`.claude/handoffs/`、
`.cursor/` 之类。这在你不换 agent 时没问题；一旦换了，交接文档对最需要它的那个
agent 就是不可见的。文档只有一个职责，而存放位置恰好废掉了它。

`agent-handoff` 默认写入项目根目录下的 `.handoff/`：这个目录属于项目而不属于任何
客户端，每个 agent 都找得到。位置可通过五级独立优先级配置，因此既有约定无需迁移
即可继续工作。

## 安装

需要 Python 3.10+，无第三方依赖。

克隆到你的 agent 技能目录：

```bash
# Claude Code
git clone https://github.com/AgathonLi/agent-handoff ~/.claude/skills/agent-handoff

# WorkBuddy
git clone https://github.com/AgathonLi/agent-handoff ~/.workbuddy/skills/agent-handoff

# OpenCode / Codex（agent 通用路径）
git clone https://github.com/AgathonLi/agent-handoff ~/.agents/skills/agent-handoff
```

也可以完全不依赖技能宿主，直接当脚本用：

```bash
git clone https://github.com/AgathonLi/agent-handoff
python agent-handoff/scripts/create_handoff.py my-task
```

## 用法

```bash
# 创建
python scripts/create_handoff.py implementing-auth

# 创建并链接到上一份交接
python scripts/create_handoff.py auth-part-2 --continues-from 2026-09-18-auth.md

# 列出
python scripts/list_handoffs.py

# 收尾前校验
python scripts/validate_handoff.py .handoff/2026-09-18-120000-auth.md

# 接手前检查新鲜度
python scripts/check_staleness.py .handoff/2026-09-18-120000-auth.md
```

所有脚本都接受 `--handoff-dir` 和 `--project-root`。`validate_handoff.py`、
`list_handoffs.py` 和 `check_staleness.py` 另外接受 `--json`。

## 目录解析

首个命中生效。各级之间互不依赖。

| 级别 | 来源 | 说明 |
|------|------|------|
| 1 | `--handoff-dir <路径>` | 优先级最高 |
| 2 | `HANDOFF_DIR` 环境变量 | 会话级或宿主级注入 |
| 3 | 项目根的 `.handoffrc` | 按项目配置，随仓库走 |
| 4 | 已存在的已知布局 | 沿用现有约定，不迁移任何文件 |
| 5 | `<项目根>/.handoff/` | 宿主中立的默认值 |

第 4 级按顺序探测 `.handoff/`、`.agent/handoffs/`、`.workbuddy/handoffs/`、
`.claude/handoffs/` 和 `thoughts/shared/handoffs/`。已在使用其中任一目录的项目会
继续沿用，不会移动文件。

每条命令都会打印是哪一级决定了结果：

```
Project root:  /path/to/project
Handoff dir:   /path/to/project/.handoff
Resolved via:  default (.handoff)
```

`.handoffrc` 两种写法都支持：

```
.handoff
```

```
handoff_dir = docs/handoffs
```

## 项目根探测

脚本向上查找 `.git`、`.handoffrc`、`AGENTS.md`、`CLAUDE.md`、`package.json`、
`pyproject.toml`、`Cargo.toml`、`go.mod` 等标志文件。

**找不到标志时，脚本直接报错，而不是写入当前目录。** 静默回退到 `cwd` 正是交接文件
出现在无关位置的原因——包括从技能自身目录调用脚本时写进技能目录。遇到这种报错，用
`--project-root` 或 `--handoff-dir` 显式指定。

## 章节标题层级

章节标题必须是 1、2 或 3 级（`#`、`##`、`###`）。生成的骨架使用 `##`。

章节**内部**的子标题请用 4 级（`####`）或更深。任何 1–3 级标题都会终止前一个章节，
因此 3 级子标题会截断父节内容，父节可能因此达不到 50 字符的最低内容要求。

必需章节，每节至少需要 50 字符的实质内容：

- `Current State Summary`
- `Important Context`
- `Immediate Next Steps`

## 校验

`validate_handoff.py` 打 0–100 分，检出凭据则直接阻断。

| 检查项 | 扣分 |
|--------|------|
| 残留 `[TODO: ...]` 占位符 | -30 |
| 必需章节缺失或内容不足 | 每项 -10 |
| 检出凭据 | -20，且判定为 BLOCKED |
| 引用的文件无法解析 | 每项 -5，最多扣 20 |
| 推荐章节缺失 | 每项 -2 |

密钥模式覆盖 API key、密码、bearer token、JWT、PEM 私钥、内嵌密码的数据库连接串，
以及 AWS、GitHub、OpenAI、Anthropic、Google 和 Slack 的专有格式。

**检出密钥的交接一律判定 BLOCKED，与分数无关。**

## 新鲜度

`check_staleness.py` 返回 `FRESH`、`SLIGHTLY_STALE`、`STALE` 或 `VERY_STALE`，
依据是文档年龄、其后的提交数、变更文件数、分支分叉，以及引用文件是否已不存在。

git 历史是最强信号。对无版本控制的项目，检查会回退到文件系统修改时间而不是直接
放弃，报告中会写明用的是哪种信号。

退出码：`0` 表示 fresh 或 slightly stale，`1` 表示 stale，`2` 表示 very stale
或解析失败。

## 跨 agent 可发现性

中立目录是必要条件，但不是充分条件——下一个 agent 还得知道去哪儿找。在项目的
`AGENTS.md` 里加上：

```markdown
## Handoffs

Session handoff documents live in `.handoff/`. Read the most recent one before
starting work; write a new one before finishing.
```

`AGENTS.md` 会被 Codex 和 OpenCode 原生读取，Claude Code 在被指向它时也会读。
这一行加上一个中立目录，才是让交接文档真正能被另一个 agent 够到的原因。

## 开发

```bash
python tests/test_agent_handoff.py
```

无第三方依赖。CI 在 Linux、Windows 和 macOS 上针对 Python 3.10 与 3.13 运行整个
测试套件。

如果你在克隆仓库里开发，同时在 `~/.workbuddy/skills/`、`~/.claude/skills/` 或
`~/.agents/skills/` 下保留安装副本，用下面的命令把改动推出去：

```bash
python scripts/sync_to_host.py            # 预演
python scripts/sync_to_host.py --apply
```

同步是单向的，并且会保留 `AGENTS.md`、`tests/`、`.github/`、脚本自身，以及
`.handoff/`、`.workbuddy/` 这类宿主写入的本地目录。保留 `AGENTS.md` 是正确性要求
而非整洁性偏好：它是项目根标志，安装副本里若含有它，该副本就会被识别为项目根并
接收交接文件，而不是正确报错。

同步载荷还受一项白名单测试约束，而不只依赖排除列表。因此新增的本地目录会让测试
失败，而不是悄无声息地进入每一份安装副本。

## 与既有工作的关系

这是一份独立实现，针对的问题与若干既有交接工具相同，但并非派生自其中任何一个。
促成它的行为差异：

- 存储目录是宿主中立且可配置的，而不是固定在某个客户端的命名空间里。
- 项目根由标志文件探测得出，而不是靠数父目录层数推断。一旦交接目录深度与假定布局
  不符，数层数的做法就会静默给出错误的根。
- 项目根缺失是错误，而不是静默写入 `cwd`。
- 1–3 级标题全部识别，且该要求被写进文档。
- 无 git 的项目会得到基于文件系统的新鲜度判定，而不是 `UNKNOWN`。

## 许可证

MIT

# Agent Handoff Skill — Agent 工作指针

本文件供会自动加载 `AGENTS.md` 的助手使用。它不是项目事实源。

## 接手时必读（按顺序）

1. `SKILL.md` — 技能契约，行为规范的事实源
2. `README.md` — 对外说明与安装方式
3. `scripts/handoff_paths.py` — 所有路径决策的唯一来源
4. `tests/test_agent_handoff.py` — 已锁定的行为，改实现前先读测试
5. 重新核对目录内实际文件，不要只信交接文本

## 本仓是源，安装位置是副本

- **源**：本目录 `D:\AI_Workspace\Agathon\Agent Handoff Skill`
- **副本**：`C:\Users\Agathon\.workbuddy\skills\agent-handoff`（WorkBuddy 加载的位置）

单向同步，源 → 副本。禁止反向：不要把副本的改动当成新版本，也不要在副本里直接改代码。
副本无 `.git`，任何只存在于副本的修改都会在下次同步时被覆盖且无法找回。

同步命令（源目录下执行）：

```bash
python scripts/sync_to_host.py            # 预演，只打印将要发生的变更
python scripts/sync_to_host.py --apply    # 实际写入
```

## 刚性红线

- 交接目录**必须**保持宿主中立。默认 `.handoff/`。禁止把默认值改成
  `.claude/`、`.workbuddy/`、`.cursor/` 或任何单一客户端的命名空间——那是本技能
  存在的原因，不是可调项。
- 路径决策只允许经 `handoff_paths.py` 的五级解析链，禁止在其他脚本里另写路径拼接。
- 项目根探测失败时**必须**以退出码 2 报错，禁止静默降级写入 cwd。
- 校验器的章节正则 `#{1,3}` 与章节定界符必须同步修改。只改一处会让子标题截断父节。
- 改动任何脚本后必须跑 `python tests/test_agent_handoff.py`，28 项需全绿。
  不要只跑单个测试类就判定通过。
- 不要提交 `.handoff/`（自用交接档案）、`__pycache__/`、`_meta.json`。已在 `.gitignore`。
- 不要把本机绝对路径写进 `README.md` 或 `SKILL.md`。那些只放在本文件。
- 远程默认 **public**。未确认不要 force-push、改 remote。
- 不要把本技能提交回 skillhub 市场——会重新落入版本与审核节奏不受控的位置。

## 已知需要人工决策的事项

- `README.md` 三处安装命令的 owner 占位 `github.com/<you>/agent-handoff`，
  建仓后需替换为真实地址。
- `LICENSE` 版权行为 `Copyright (c) 2026 Agathon`，对外公开前确认是否保留。

## 冲突处理

本文件只做自动注入指针。与 `SKILL.md` / `README.md` / `LICENSE` 冲突时，以后者为准，
并先停下询问用户。不要把本文件扩写成第二套规范。

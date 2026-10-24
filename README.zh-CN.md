# Tidvo

**面向 AI Agent 工作流定制的清理技能。**

[English](README.md)

Tidvo 针对 Codex、Claude Code、OpenClaw、Pi 及其他 Agent 产品的本地数据与
开发场景做了专门适配：检查占用，保护会话、记忆、共享 Skills、MCP 工具和开发
依赖，再通过对话审查可以清理的缓存。执行后提供操作记录与恢复入口。

当前为 **0.2.0 Beta，支持 macOS，Windows 支持规划中**。

## 针对 Agent 做了哪些优化

- **识别数据用途**：将会话、任务、长期记忆、数据库、检查点、工作区、配置和
  安装资源分别统计；体检结果全部只读，不因名字含 `tmp` 或 `cache` 就删除。
- **保护共享资源**：识别共享 Skills 软链接的真实目标，保留插件、本地安装包、
  模型及配置中声明的资源；已识别的 Agent 扩展即使标记为旧版也保留。
- **理解 MCP 与开发依赖**：结合已知配置检查工具引用；项目 `node_modules`、
  `.venv` 和 `venv` 默认保留。没有运行进程不等于以后不再使用。
- **通过对话完成批量审查**：按用途与影响推荐，内部处理候选 ID，用户确认一份
  明确清单后执行；每次操作结束都会总结结果、保留项、检查缺口及下一步建议。
- **移动前再次保护**：重新检查配置引用、路径身份、活动状态和文件占用。
  计划后新增保护也能阻止原计划执行；只移入废纸篓，保留可核查的恢复记录。

初始适配目录登记 38 项 Agent 及相关工具，其中 31 项为 Agent／编辑器工具。
覆盖 Codex、Claude Code、OpenClaw、Pi、Gemini CLI、OpenCode、Cursor、Windsurf、
Cline、WorkBuddy、CodeBuddy、TRAE、Qoder、Kimi、Qwen Code、iFlow 等。
还可通过项目标记、扩展声明、环境变量和自定义目录扩展识别范围。
这不代表所有产品、版本和目录布局均已实机验证；证据与缺口会分别显示。
详见[适配与保护规则](references/agent-adapters.md)。

## 安装和第一次使用

需要已有的 Python 3.11+。实际移动文件还要求 macOS 14+ 和普通用户账户。
程序不会自动安装运行时，也不需要额外安装 Mole。

1. 在本仓库的 GitHub Releases 下载 `tidvo-0.2.0.tar.gz` 和对应 `.sha256` 文件。
2. 在没有同名 `tidvo/` 目录的位置校验并解压：

   ```bash
   shasum -a 256 -c tidvo-0.2.0.tar.gz.sha256
   tar -xzf tidvo-0.2.0.tar.gz
   ```

3. 将整个 `tidvo/` 目录按所用 Agent 的本地 Skills 机制安装，或直接让 Agent
   读取该目录的 `SKILL.md`。不要递归安装 `vendor/` 中的上游技能。
4. 先发送只读体检请求：

   > 使用 Tidvo 只读体检我的 Agent 与开发环境，保留会话、记忆和项目依赖，
   > 按用途解释占用，列出保护项与检查缺口，先不清理，最后推荐下一步。

也可以先克隆源码，在仓库内让 Agent 读取根目录的 `SKILL.md`；日常安装推荐
使用 Release 中只有一个技能入口的独立包。替换旧安装前保留其内容，避免覆盖
个人修改。用户不需要逐项复制 ID 或手动执行清理命令。

## 手动运行

在解压目录内执行：

```bash
python3 scripts/tidvo.py agents --root ~/Projects
python3 scripts/tidvo.py agents --catalog
python3 scripts/tidvo.py scan --root ~/Projects --output scan.json
```

前两条分别只读体检、查看适配目录；第三条保存清理候选报告，不移动文件。
`--output` 拒绝覆盖已有文件，需要换一个新文件名。
若终端的 `python3` 低于 3.11，请使用本机已有 3.11+ 解释器的绝对路径。
完整手动计划、执行和恢复接口见[命令说明](references/commands.md)。

## 平台与边界

| 平台 | 当前状态 |
| --- | --- |
| macOS | Beta；实际移动要求 macOS 14+。本地在 Apple Silicon 验证，其他环境以实际 CI 结果为准。 |
| Windows | 规划中；尚未实现 Windows 数据目录、进程证据、锁及回收站执行，当前不能作为 Windows 清理工具使用。 |
| Linux | 仅运行部分可移植测试，不属于桌面清理支持平台。 |

Windows 后续将分别实现目录发现、活动和占用检查、回收站移动与恢复，并通过独立
的 Windows 测试验证；不会把 macOS 路径替换一下就宣称支持跨平台。

**移入废纸篓通常不会立即释放磁盘空间。** 体检占用、候选容量、移入容量与实际
空闲空间变化分别报告。恢复依赖废纸篓中的原载荷仍完整存在；程序不会自动清空
废纸篓、永久删除、提权或关闭应用。资料检查不完整时会保留并说明原因。
只读体检不读取对话正文或打开数据库，也不调用 Agent 命令和云端账户。

## 验证、反馈与源码

```bash
python3 -m unittest discover -s tests -v
python3 tests/benchmark_fixture.py
python3 scripts/build_release.py
```

测试使用临时模拟 Home，不清理真实用户目录。已记录的本地验证和未验证范围见
[验证记录](references/validation.md)。GitHub Actions 的配置文件不等于执行成功。

反馈漏识别或布局变化时，请提供系统版本、工具版本、脱敏后的目录结构和错误类型。
不要公开完整扫描报告、会话、凭证、数据库或本机恢复记录。

项目按 GPL-3.0-only 开源，包含固定版本的 Mole 后端，是独立衍生产品。
来源和修改见 [UPSTREAM.md](UPSTREAM.md)，许可证见 [LICENSE](LICENSE)。

早期本地版本名为 Mac Dev Cleanup。为保留原有配置和恢复记录，兼容入口
`scripts/mac_cleanup.py`、内部 `macdev` 模块、配置路径
`~/.config/mac-dev-cleanup/config.json`、状态目录 `~/.local/state/mac-dev-cleanup`
及废纸篓载荷前缀继续保留；品牌改名不会迁移或删除用户数据。

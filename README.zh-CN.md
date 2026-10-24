# Tidvo

**面向 AI Agent 工作流定制的清理技能。**

[English](README.md)

用对话检查占用、审查清理范围，专门保护 Agent 会话、记忆、共享 Skills、MCP
工具和开发依赖。针对 Codex、Claude Code、OpenClaw、Pi 等产品做了定制适配。

## 一句话安装

把下面这句话发给你的 AI 工具：

> 帮我安装 Tidvo：https://raw.githubusercontent.com/sanzhangzui/tidvo/main/INSTALL.md

AI 会负责下载、校验、安装和环境检查。
适用于能操作本机文件和终端的 AI 工具。
当前支持 **macOS 14+，需要 Python 3.11+**；Windows 支持规划中。

## 安装后怎么用

先检查占用：

> 用 Tidvo 只读体检我的 Agent 和开发环境，保留会话、记忆及项目依赖，解释占用最大的内容，并推荐下一步，先不清理。

需要清理时：

> 用 Tidvo 推荐可以清理的应用缓存和下载缓存，保留开发依赖和 Agent 数据，说明影响后给我一份批量确认清单。

AI 会处理候选 ID。每次操作结束都会总结结果，并推荐下一步。

## 针对 Agent 做了哪些优化

- **保护工作数据**：会话、记忆、数据库、共享 Skills、插件、MCP 引用和项目
  依赖都有专门的保留规则。
- **先解释再清理**：按用途和影响分组，说明未知项与检查缺口，再审查清理范围。
- **保留恢复记录**：按确认清单移入废纸篓并记录恢复信息。移入废纸篓通常不会
  立即释放磁盘空间。

初始目录登记 38 项 Agent 及相关工具，会明确展示识别依据和覆盖限制。
当前为 Beta，尚未逐一认证所有产品和版本。

## 详细资料

[给 AI 阅读的安装说明](INSTALL.md) ·
[手动命令](references/commands.md) ·
[适配与保护规则](references/agent-adapters.md) ·
[验证记录](references/validation.md) ·
[版本下载](https://github.com/sanzhangzui/tidvo/releases)

按 GPL-3.0-only 开源，包含固定版本的 Mole 后端，是独立衍生产品。
来源与修改见 [UPSTREAM.md](UPSTREAM.md)，许可证见 [LICENSE](LICENSE)。

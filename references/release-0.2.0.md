# Tidvo 0.2.0 Beta

面向 AI Agent 工作流定制的清理技能，针对 Codex、Claude Code、OpenClaw、Pi
及相关工具适配本地数据识别与保护。当前支持 macOS，Windows 支持规划中。

- Agent 只读体检：按用途统计数据占用，明确适配证据、未知项和检查缺口。
- 保护会话、记忆、数据库及关联文件、共享 Skills、插件、MCP 引用和项目依赖。
- 对话式分组推荐和一份明确清单的批量确认；移动前再次检查，保留恢复记录。
- 已审查的 VS Code、Dia、飞书／Lark 和 npm 下载缓存等普通规则继续可用。
- 提供中文安装说明、独立技能包和 SHA-256 校验文件。

初始目录登记 38 项 Agent 及相关工具；这不是所有产品和版本的实机认证。
Python 3.11+；实际移动要求 macOS 14+，Windows 尚未实现。
验证范围与限制见仓库的 `references/validation.md` 和 GitHub Actions 实际结果。

下载 `tidvo-0.2.0.tar.gz` 和 `.sha256`，校验后解压，将整个 `tidvo/` 安装为
本地 Skill。第一次使用建议先做只读体检，不执行清理。
移入废纸篓通常不会立即释放空间，恢复依赖原载荷仍存在。

GPL-3.0-only；包含固定版本的 Mole 源码及修改声明，详见 `UPSTREAM.md`。

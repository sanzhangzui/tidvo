# Agent 只读体检与数据保护（0.2.0 beta）

本阶段回答“发现了哪些 Agent 本地数据、占用在哪里、哪些必须保留”。
体检结果全部为 `report_only`，没有清理 ID，也不能直接生成删除计划。
体检占用不是可释放空间；本版本没有新增 Agent 会话、记忆或数据库清理功能。

## 如何使用

通过对话请求：

> 用这个 Skill 给我的 Agent 工具做只读体检，保留开发依赖和所有 Agent
> 数据，按用途汇总占用，说明保护项和适配缺口，先不执行清理。

需要手动运行时，在技能目录下使用已有的 Python 3.11+：

```bash
python3 scripts/tidvo.py agents --root ~/desktopProjects
python3 scripts/tidvo.py agents --json --output agent-audit.json
python3 scripts/tidvo.py agents --catalog
```

`--output` 仅创建新的 0600 JSON 文件，拒绝覆盖已有文件。没有显式输出时，
只向终端返回结果；不会安装依赖、修改 Agent 配置或创建产品操作记录。
普通 `scan` 也会附带 `agent_audit`，其状态和清理候选的状态分别报告。
Python 版本不足时，换用本机已有的 3.11+ 解释器绝对路径，不自动安装运行时。

## 覆盖范围及证据

初始目录登记 **38 项**，其中 31 项是 Agent／编辑器工具，其余为三个桌面 AI
客户端、飞书集成、两个模型运行时及一项共享资源规则。目录是识别和保护能力
清单，不是 38 个已验证所有版本的清理适配器。

| 类型 | 初始登记对象 |
| --- | --- |
| CLI、个人及服务型 Agent | Codex、Claude Code、Pi、OpenClaw、Hermes、Gemini CLI、OpenCode、Aider、Goose、Amp、GitHub Copilot、Kimi Code／旧 Kimi CLI、Qwen Code、iFlow、Crush、OpenHands |
| 编辑器、扩展及桌面开发 Agent | Continue、Cline、Roo Code、Kilo Code、Augment、Cursor、Windsurf、Zed、Antigravity、TRAE、Qoder、CodeBuddy、WorkBuddy、Amazon Q Developer、Cody |
| 相关客户端、运行时和共享数据 | Cherry Studio、Chatbox、AnythingLLM、飞书／Lark、Ollama、LM Studio、共享 Agent 资源 |

实际路径、扩展标识、来源及能力以 `macdev/agent_catalog.py` 和
`agents --catalog --json` 为准，文档不维护第二份路径规则。

- `documented_defaults`：Codex、Claude Code、Pi、OpenClaw、Gemini CLI、
  OpenCode、Aider 的核心默认布局已核对一手资料；这不是每个候选路径或版本的
  逐项认证。默认路径命中仍然只是发现数据，不证明程序已安装、能运行或闲置。
- `conservative_location_hints`：其余主要是产品身份和保守位置线索。
  产品主页不作为该磁盘布局的证明；发现后保留并标明待本机核验。
- 项目资源、用户声明、共享链接、未知标记及扩展 manifest 分别记录 `basis`，
  不把未知目录强行归属某个品牌。未知工具保持未知。
- 自动测试使用合成 Home。当前登记对象的真实安装版本和全部布局并未逐一验收。
  目录的资料复核日期是 2026-10-23，不等于持续同步厂商最新版本。

## 不限于固定品牌名单

识别由多层证据组成：已登记数据目录／项目标记、受支持的环境变量、编辑器扩展
身份或 AI 能力声明、未知目录中的 Agent 标记、配置中声明的本地资源路径，
以及用户补充的数据根目录。新增品牌通常先加声明式条目和 fixture，无需增加
可执行插件或删除逻辑。

未知发现只检查 Home、`.config`、`.local/share`、Application Support 下有限的
一级子目录名称和少量直属条目；结合 `SOUL.md`、`MEMORY.md`、`AGENTS.md`、
`mcp.json` 等标记保守归类。单独一个普通隐藏目录不会被宣称为某个 Agent。
编辑器扩展通过已知标识或 manifest 的聊天、模型工具、MCP 能力声明识别。
项目发现仍有深度、目录数和时间预算，不进入 `node_modules` 或虚拟环境。
达到预算、权限不足或配置格式不支持时，会返回 `partial`／`unavailable`。

以下目录环境变量会影响登记位置：`CODEX_HOME`、`CLAUDE_CONFIG_DIR`、
`PI_CODING_AGENT_DIR`、`PI_CODING_AGENT_SESSION_DIR`、`OPENCLAW_STATE_DIR`、
`OPENCLAW_CONFIG_PATH`、`HERMES_HOME`、`OPENCODE_DB`、`XDG_CONFIG_HOME`、
`XDG_DATA_HOME`、`XDG_CACHE_HOME`。只读取这些受支持的目录覆盖值，不执行
环境变量内容，也不把整个 XDG 目录当成 Agent 数据。

未被识别的本地工具可在 `~/.config/mac-dev-cleanup/config.json` 中补充：

```json
{
  "roots": ["~/desktopProjects"],
  "agent_roots": {
    "my_agent": ["~/AgentData/my-agent", "~/Work/private-memory"]
  }
}
```

名称使用小写字母开头的字母、数字、下划线或连字符。路径必须为 Home 内的
明确目录或文件；不允许将整个 Home、Library、`.config`、`.local/share` 等
共享大目录声明为 Agent 根。此配置只增加体检与保护，不能授予清理权限。
非法、过宽或范围外的显式目录会阻止清理；产品不会自动写入这些设置。

## 数据保护规则

| 数据用途 | 规则及原因 |
| --- | --- |
| 凭证、设置、MCP、项目指令 | 保留。关系到账户、服务连接、权限和工作约定。 |
| 会话、任务、工具结果、长期记忆 | 保留。可能含未完成工作和用户独有内容，不能按大小或时间淘汰。 |
| SQLite／其他数据库及 WAL、SHM、journal | 一并保护。不打开 SQL 连接，不执行 VACUUM，不拆删关联文件。 |
| 检查点、快照、文件历史 | 保留。可能是未提交变更的恢复来源。 |
| 工作区、worktree、源码、依赖及构建／交付产物 | 保留 Agent 根和工作区；现有普通项目规则另行判断。不能把工作区当作“孤儿缓存”。 |
| Skills、扩展、插件、提示词、本地包、模型 | 保留。共享软链接目标也登记保护；安装资源不等于下载缓存。 |
| 浏览器资料、Cookie、IndexedDB、本地存储 | 保留。可能含登录态、授权和业务状态。 |
| `tmp`、`cache`、logs 或未分类文件 | 体检可统计，不能据名字新增清理权限。日志也可能对诊断或追踪任务有用。 |

保护同时约束扫描候选、计划重算和实际移动。候选内部出现受保护的 Agent
标记、数据库或仓库时，整个候选保留。移动前重新读取已记录项目的路径引用、
自定义根目录及共享链接；计划后新增保护也可以阻止原计划执行。已识别的 Agent
扩展安装目录默认保留。0.2.4 对 VS Code 已标记 obsolete、存在更新注册版本、
未发现已知持久数据且无运行／配置引用的旧程序包提供单独审查规则；不放宽会话、
记忆、共享资源、未知扩展或用户声明保护路径。详见 cleanup-coverage.md。
旧版计划必须重新扫描生成。

此前已独立审查的窄规则仍保留：非当前／非待更新且锁检查通过的 Codex daemon
旧程序，来源可确认的飞书 Service Worker 缓存叶目录，以及已知 worktree／明确
声明工作区内的 Python 字节码、pytest、mypy、ruff 缓存。这些规则仍需自己的
元数据、引用、活动状态和占用检查；不授予整个 Agent 数据目录清理权限。
包含 Agent 标记或数据库的子树仍因敏感文件检查而保留。

## 怎样读体检结果

每项工具显示发现依据、路径、数据类别、测得占用、共享目标、状态，以及可取得
的应用版本／进程 PID。应用版本仅从已知位置的 Info.plist 读取，不运行程序的
`--version`。没有匹配进程不证明没有定时任务、后台服务或远程任务。

统计使用文件系统元数据，不读取凭证文件、对话正文、记忆正文或数据库内容。
为保护本地路径及 MCP 引用，程序会解析明确登记的、最多 1 MiB 的配置或扩展
manifest（JSON／TOML）；环境、请求头、密码等秘密字段不写入报告。
JSONC／JSON5／YAML 等本阶段未实现的配置解析显示为缺口，不临时执行解析插件。
报告仍含本地路径、文件用途及 PID，分享前应检查这些元数据。

`total_unique_allocated_bytes` 是本次已访问 inode 的去重占用估算。
不同根和用途分类可能重叠，不能把各行相加当作总量。共享目标只在唯一总量中
计数一次；APFS 克隆共享块不在此去重范围。`partial` 的数值是下限，未能访问
的数据为未知，均不是可清理或已释放容量。排除项不会被测量，但仍受保护。

软链接仅在登记的资源根处解析，目标须在 Home 内；内部链接不递归进入。
外部卷、Home 外目标、系统用户数据、容器卷及云端空间没有完整覆盖。
本功能不认证 Agent 运行健康、插件可信性或密钥有效性，也不读取 Keychain。

体检结束时应总结已发现的数据和保护项，列出缺口，再推荐一个具体下一步：
例如核对某个自定义数据位置，或单独审查现有普通缓存。不得把体检结果直接
转为清理，也不自动调用 Agent 自带的压缩／淘汰／会话清理命令。

## 资料与设计依据

- [Codex worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)：
  worktree 可能携带未提交文件、构建数据及依赖，不能仅凭闲置外观整目录清理。
- [Claude Code directory](https://code.claude.com/docs/en/claude-directory)、
  [memory](https://code.claude.com/docs/en/memory)：会话、记忆与文件历史有恢复价值。
- [Pi configuration](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/configuration.md)：
  数据根、项目配置与共享安装资源需要分开识别。
- [OpenClaw sessions](https://docs.openclaw.ai/concepts/session)、
  [memory](https://docs.openclaw.ai/concepts/memory)、
  [session pruning](https://docs.openclaw.ai/concepts/session-pruning)：
  会话存储格式可变化；上下文裁剪不等于可删除磁盘历史。
- [Gemini CLI sessions](https://geminicli.com/docs/cli/session-management/)：
  `tmp` 下也存持久会话，不能作为通用临时目录清理。
- [OpenCode troubleshooting](https://opencode.ai/docs/troubleshooting/)：
  状态库、快照、认证、日志与可配置路径需保守处理。
- [Aider configuration](https://aider.chat/docs/config/aider_conf.html)：
  项目历史和设置需要保护。
- [WorkBuddy 企业文档](https://intl.cloud.tencent.com/zh/document/product/1316/84502)：
  产品中的“缓存”概念不能直接映射为可自动删除的文件系统目录。
- [Kimi Code migration](https://moonshotai.github.io/kimi-code/en/guides/migration)：
  新旧实现与迁移状态使“旧运行时一定没用”的推断不可靠。

其他登记对象的一手产品入口见命令输出的 `source_urls`。扩展覆盖应持续补充
真实版本 fixture 和布局证据，再考虑单独审查可清理的缓存规则。

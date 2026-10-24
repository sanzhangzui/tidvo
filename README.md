# Tidvo

**Conversational disk cleanup, optimized for AI Agent and development environments.**

[中文说明](README.zh-CN.md)

Check disk usage, find worthwhile cache cleanup, and clean an approved batch with
recovery records. Extra protection for Codex, Claude Code, OpenClaw, Pi and related
tools preserves sessions, memory, shared Skills, MCP resources and project dependencies.

## Install with one message

Paste this into your AI tool:

> Install Tidvo for my current AI tool: https://raw.githubusercontent.com/sanzhangzui/tidvo/main/INSTALL.md

Your AI handles downloading, checksum verification, installation and setup checks.
This requires an AI tool with local file and terminal access.
Current platform: **macOS 14+ and Python 3.11+**. Windows support is planned.

## Start using it

Just say:

> Help me clean up my computer.

Tidvo checks storage, recommends a batch, explains the impact and waits for your
confirmation before acting. Data protection, retained development dependencies
and a useful result summary are defaults.

To inspect first, say:

> What's taking up space?

Current discovery focuses on known application/download caches and development
artifacts. Reports explain the actual coverage.

Reports separately total ready caches, items to recheck after quitting apps,
separate-review items, protected data and incomplete evidence. Known cache rules
include Maps, Homebrew, Cargo, Ruby and PyInstaller. Qualified retired Agent
extension program packages can be reviewed separately; sessions/memory stay protected.

## Built for Agent workflows

- **Protect working data:** sessions, memory, databases, shared Skills, plugins,
  MCP references and project dependencies stay protected.
- **Explain before cleaning:** group candidates by purpose and impact; incomplete
  evidence and unknown layouts remain visible.
- **Keep recovery records:** approved items move to Trash with recorded restore
  information. Moving to Trash usually does not immediately free disk space.

The initial catalog contains 38 Agent and related-tool entries, with explicit
evidence and coverage limits. This is a beta, not certification of every version.

## More information

[Installation details for AI tools](INSTALL.md) ·
[Commands](references/commands.md) ·
[Agent coverage](references/agent-adapters.md) ·
[Validation](references/validation.md) ·
[Downloads](https://github.com/sanzhangzui/tidvo/releases)

GPL-3.0-only. Tidvo incorporates a pinned Mole backend as an independent
derivative; see [UPSTREAM.md](UPSTREAM.md) and [LICENSE](LICENSE).

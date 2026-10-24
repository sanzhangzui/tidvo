# Tidvo

**Cleanup tailored for AI Agent workflows.**

[中文说明](README.zh-CN.md)

Inspect storage and review cleanup through conversation, with protections for
Agent sessions, memory, shared Skills, MCP tools and development dependencies.
Tailored for Codex, Claude Code, OpenClaw, Pi and related tools.

## Install with one message

Paste this into your AI tool:

> Install Tidvo for my current AI tool: https://raw.githubusercontent.com/sanzhangzui/tidvo/main/INSTALL.md

Your AI handles downloading, checksum verification, installation and setup checks.
This requires an AI tool with local file and terminal access.
Current platform: **macOS 14+ and Python 3.11+**. Windows support is planned.

## Start using it

Check storage first:

> Use Tidvo to inspect my Agent and development storage. Keep sessions, memory and project dependencies. Explain the largest items and recommend what to do next. Do not clean anything yet.

Then request a cleanup recommendation:

> Use Tidvo to recommend application and download caches to clean. Keep my development dependencies and Agent data, explain the impact, and show one batch for me to confirm.

Tidvo handles candidate IDs internally. It summarizes every operation and
recommends the next step.

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

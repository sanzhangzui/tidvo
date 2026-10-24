"""Declarative, versioned inventory hints. No deletion permission or executable plugins."""
import os
import re
from pathlib import Path

REVIEWED_ON = "2026-10-23"
CATALOG_VERSION = 1


def tool(identifier, name, roots=(), *, project=(), apps=(), extensions=(), configs=(), sources=(), documented=False, kind="agent"):
    return {"id": identifier, "name": name, "kind": kind, "roots": list(roots), "project": list(project),
            "apps": list(apps), "extensions": list(extensions), "configs": list(configs), "source_urls": list(sources),
            "layout_evidence": "documented_defaults" if documented else "conservative_location_hints",
            "reviewed_on": REVIEWED_ON, "capabilities": ["read_only_inventory", "protect_data"],
            "validation": "synthetic_fixtures_only; installed versions and all layouts are not certified"}


# A product URL identifies the product; for location hints it is NOT proof of
# that filesystem layout. A hit is reported as data found, never proof of install.
CATALOG = [
    tool("codex", "Codex", ["${CODEX_HOME}"], project=[".codex"], apps=["Codex"],
         extensions=["openai.chatgpt", "openai.codex"], configs=["${CODEX_HOME}/config.toml"],
         sources=["https://learn.chatgpt.com/docs/environments/git-worktrees"], documented=True),
    tool("claude_code", "Claude Code", ["${CLAUDE_CONFIG_DIR}", "~/.claude.json", "~/.local/share/claude"],
         project=[".claude", "CLAUDE.md", "CLAUDE.local.md"], apps=["Claude"], extensions=["anthropic.claude-code"],
         configs=["~/.claude.json", "${CLAUDE_CONFIG_DIR}/settings.json", "${CLAUDE_CONFIG_DIR}/settings.local.json"],
         sources=["https://code.claude.com/docs/en/claude-directory"], documented=True),
    tool("pi", "Pi coding agent", ["${PI_CODING_AGENT_DIR}", "${PI_CODING_AGENT_SESSION_DIR}"], project=[".pi"],
         configs=["${PI_CODING_AGENT_DIR}/settings.json", "${PI_CODING_AGENT_DIR}/mcp.json"],
         sources=["https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/configuration.md"], documented=True),
    tool("openclaw", "OpenClaw", ["${OPENCLAW_STATE_DIR}", "${OPENCLAW_CONFIG_PATH}"], project=[".openclaw", "SOUL.md", "USER.md", "MEMORY.md", "HEARTBEAT.md"],
         apps=["OpenClaw"], configs=["${OPENCLAW_CONFIG_PATH}"],
         sources=["https://docs.openclaw.ai/concepts/session", "https://docs.openclaw.ai/concepts/memory"], documented=True),
    tool("hermes", "Hermes Agent", ["${HERMES_HOME}"], project=[".hermes"],
         sources=["https://github.com/NousResearch/hermes-agent"]),
    tool("gemini_cli", "Gemini CLI", ["~/.gemini"], project=[".gemini", "GEMINI.md"],
         configs=["~/.gemini/settings.json"], sources=["https://geminicli.com/docs/cli/session-management/"], documented=True),
    tool("opencode", "OpenCode", ["${XDG_CONFIG_HOME}/opencode", "${XDG_DATA_HOME}/opencode", "${XDG_CACHE_HOME}/opencode", "${OPENCODE_DB}"],
         project=[".opencode", "opencode.json", "opencode.jsonc"], apps=["OpenCode"],
         configs=["${XDG_CONFIG_HOME}/opencode/opencode.json", "${XDG_CONFIG_HOME}/opencode/opencode.jsonc"],
         sources=["https://opencode.ai/docs/troubleshooting/"], documented=True),
    tool("aider", "Aider", ["~/.aider.conf.yml", "~/.aider.chat.history.md", "~/.aider.input.history"],
         project=[".aider.conf.yml", ".aider.chat.history.md", ".aider.input.history", ".aider.tags.cache.v4"],
         sources=["https://aider.chat/docs/config/aider_conf.html"], documented=True),
    tool("goose", "Goose", ["${XDG_CONFIG_HOME}/goose", "${XDG_DATA_HOME}/goose", "~/Library/Application Support/Goose"],
         project=[".goose"], apps=["Goose"], sources=["https://github.com/aaif-goose/goose"]),
    tool("amp", "Amp", ["~/.amp", "${XDG_CONFIG_HOME}/amp", "${XDG_DATA_HOME}/amp"], project=[".amp"],
         sources=["https://ampcode.com/manual"]),
    tool("copilot", "GitHub Copilot", ["~/.copilot"], project=[".github/copilot-instructions.md"],
         extensions=["github.copilot", "github.copilot-chat"], sources=["https://docs.github.com/en/copilot"]),
    tool("continue", "Continue", ["~/.continue"], project=[".continue"], extensions=["continue.continue"],
         sources=["https://docs.continue.dev/customize/deep-dives/configuration"]),
    tool("cline", "Cline", ["~/.cline", "~/Library/Application Support/Cline"], project=[".cline", ".clinerules"],
         apps=["Cline"], extensions=["saoudrizwan.claude-dev"], sources=["https://docs.cline.bot/getting-started/installing-cline"]),
    tool("roo_code", "Roo Code", ["~/.roo"], project=[".roo", ".roorules"], extensions=["rooveterinaryinc.roo-cline"],
         sources=["https://github.com/RooCodeInc/Roo-Code"]),
    tool("kilo_code", "Kilo Code", ["~/.kilocode"], project=[".kilocode", ".kilocoderules"], extensions=["kilocode.kilo-code"],
         sources=["https://github.com/Kilo-Org/kilocode"]),
    tool("augment", "Augment Code", ["~/.augment"], project=[".augment"], extensions=["augment.vscode-augment"],
         sources=["https://docs.augmentcode.com/"]),
    tool("cursor", "Cursor", ["~/.cursor", "~/Library/Application Support/Cursor"], project=[".cursor", ".cursorrules"],
         apps=["Cursor"], configs=["~/.cursor/mcp.json"], sources=["https://cursor.com/docs"]),
    tool("windsurf", "Windsurf", ["~/.windsurf", "~/.codeium", "~/Library/Application Support/Windsurf"],
         project=[".windsurf", ".windsurfrules"], apps=["Windsurf"], extensions=["codeium.codeium"],
         sources=["https://docs.windsurf.com/"]),
    tool("zed", "Zed Agent", ["${XDG_CONFIG_HOME}/zed", "~/Library/Application Support/Zed"], project=[".zed"],
         apps=["Zed"], sources=["https://zed.dev/docs/ai/overview"]),
    tool("antigravity", "Antigravity", ["~/.gemini/antigravity", "~/Library/Application Support/Antigravity"],
         apps=["Antigravity"], sources=["https://antigravity.google/"]),
    tool("trae", "TRAE", ["~/.trae", "~/Library/Application Support/Trae", "~/Library/Application Support/Trae CN"],
         project=[".trae"], apps=["Trae", "Trae CN"], sources=["https://www.trae.ai/"]),
    tool("qoder", "Qoder", ["~/.qoder", "~/Library/Application Support/Qoder"], project=[".qoder"], apps=["Qoder"],
         sources=["https://docs.qoder.com/"]),
    tool("codebuddy", "CodeBuddy", ["~/.codebuddy", "~/Library/Application Support/CodeBuddy", "~/Library/Application Support/CodeBuddy CN"],
         project=[".codebuddy", "CODEBUDDY.md"], apps=["CodeBuddy", "CodeBuddy CN"], sources=["https://www.codebuddy.ai/"]),
    tool("workbuddy", "WorkBuddy", ["~/.workbuddy", "~/Library/Application Support/WorkBuddy"], project=[".workbuddy"], apps=["WorkBuddy"],
         sources=["https://intl.cloud.tencent.com/zh/document/product/1316/84502"]),
    tool("kimi", "Kimi Code / legacy Kimi CLI", ["~/.kimi"], project=[".kimi", "KIMI.md"],
         sources=["https://moonshotai.github.io/kimi-code/en/guides/migration"]),
    tool("qwen_code", "Qwen Code", ["~/.qwen"], project=[".qwen", "QWEN.md"], configs=["~/.qwen/settings.json"],
         sources=["https://github.com/QwenLM/qwen-code"]),
    tool("iflow", "iFlow CLI", ["~/.iflow"], project=[".iflow", "IFLOW.md"], configs=["~/.iflow/settings.json"],
         sources=["https://github.com/iflow-ai/iflow-cli"]),
    tool("crush", "Crush", ["${XDG_CONFIG_HOME}/crush", "${XDG_DATA_HOME}/crush"], project=[".crush", "crush.json"],
         sources=["https://github.com/charmbracelet/crush"]),
    tool("amazon_q", "Amazon Q Developer", ["~/.aws/amazonq", "~/.aws/sso/cache"], project=[".amazonq"],
         extensions=["amazonwebservices.amazon-q-vscode"], sources=["https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/"]),
    tool("openhands", "OpenHands", ["~/.openhands"], project=[".openhands"], sources=["https://github.com/All-Hands-AI/OpenHands"]),
    tool("cody", "Sourcegraph Cody", extensions=["sourcegraph.cody-ai"], sources=["https://sourcegraph.com/docs/cody"]),
    tool("cherry_studio", "Cherry Studio", ["~/Library/Application Support/CherryStudio"], apps=["Cherry Studio"],
         sources=["https://github.com/CherryHQ/cherry-studio"], kind="desktop_ai_client"),
    tool("chatbox", "Chatbox", ["~/Library/Application Support/Chatbox"], apps=["Chatbox"],
         sources=["https://github.com/chatboxai/chatbox"], kind="desktop_ai_client"),
    tool("anythingllm", "AnythingLLM", ["~/Library/Application Support/anythingllm-desktop"], apps=["AnythingLLM"],
         sources=["https://github.com/Mintplex-Labs/anything-llm"], kind="desktop_ai_client"),
    tool("feishu", "Feishu / Lark desktop", ["~/Library/Application Support/LarkShell", "~/Library/Application Support/LarkInternational",
         "~/Library/Containers/com.bytedance.macos.feishu/Data/Library/Application Support/LarkShell"], apps=["Feishu", "Lark"],
         sources=["https://aily.feishu.cn/"], kind="desktop_integration"),
    tool("ollama", "Ollama", ["~/.ollama"], apps=["Ollama"], sources=["https://github.com/ollama/ollama"], kind="shared_runtime"),
    tool("lm_studio", "LM Studio", ["~/.lmstudio", "~/Library/Application Support/LM Studio"], apps=["LM Studio"],
         sources=["https://lmstudio.ai/docs"], kind="shared_runtime"),
    tool("shared_agent_resources", "Shared Agent resources", ["~/.agents"], project=[".agents", "AGENTS.md", "AGENTS.override.md", ".mcp.json", ".vscode/mcp.json"], kind="shared_resources"),
]

EDITOR_SUPPORT_NAMES = ("Code", "Code - Insiders", "VSCodium", "Cursor", "Windsurf", "Trae", "Trae CN", "Qoder", "Antigravity", "CodeBuddy", "CodeBuddy CN")
EDITOR_EXTENSION_ROOTS = (".vscode/extensions", ".vscode-insiders/extensions", ".cursor/extensions", ".windsurf/extensions",
                          ".trae/extensions", ".trae-cn/extensions", ".qoder/extensions", ".antigravity/extensions", ".codebuddy/extensions")
PROTECTED_AGENT_NAMES = frozenset({Path(p).name for t in CATALOG for p in t["project"]} |
                                {"AGENTS.md", "AGENTS.override.md", "CLAUDE.md", "CODEBUDDY.md", "GEMINI.md", "QWEN.md", "KIMI.md",
                                 "MEMORY.md", "SOUL.md", "USER.md", "IDENTITY.md", "HEARTBEAT.md", "mcp.json", ".mcp.json",
                                 "auth.json", ".credentials.json", "oauth_creds.json"})
UNKNOWN_MARKERS = frozenset({"SOUL.md", "MEMORY.md", "AGENTS.md", "mcp.json", "agent.json", "agents.json"})


def expand_path(template, home, environ=None):
    """Expand only registered directory overrides. Never expose env contents."""
    env = os.environ if environ is None else environ
    home = Path(home)
    if not isinstance(template, str) or len(template) > 4096 or "://" in template or any(ord(c) < 32 for c in template):
        raise ValueError("invalid_agent_directory")
    defaults = {"CODEX_HOME": str(home / ".codex"), "CLAUDE_CONFIG_DIR": str(home / ".claude"),
                "PI_CODING_AGENT_DIR": str(home / ".pi/agent"), "OPENCLAW_STATE_DIR": str(home / ".openclaw"),
                "HERMES_HOME": str(home / ".hermes"), "XDG_CONFIG_HOME": str(home / ".config"),
                "XDG_DATA_HOME": str(home / ".local/share"), "XDG_CACHE_HOME": str(home / ".cache")}
    values = {k: env.get(k, v) for k, v in defaults.items()}
    values.update(PI_CODING_AGENT_SESSION_DIR=env.get("PI_CODING_AGENT_SESSION_DIR", values["PI_CODING_AGENT_DIR"] + "/sessions"),
                  OPENCLAW_CONFIG_PATH=env.get("OPENCLAW_CONFIG_PATH", values["OPENCLAW_STATE_DIR"] + "/openclaw.json"),
                  OPENCODE_DB=env.get("OPENCODE_DB", values["XDG_DATA_HOME"] + "/opencode/opencode.db"))
    used = re.findall(r"\$\{([A-Z_]+)\}", template)
    for key in used:
        value = values[key]
        if not isinstance(value, str) or not value or len(value) > 4096 or "://" in value or any(ord(c) < 32 for c in value):
            raise ValueError("invalid_agent_directory_override")
        template = template.replace("${" + key + "}", value)
    if template == "~":
        template = str(home)
    elif template.startswith("~/"):
        template = str(home / template[2:])
    p = Path(template)
    if not p.is_absolute() or ".." in p.parts:
        raise ValueError("agent_directory_must_be_absolute")
    return p, ("environment_override" if any(k in env for k in used) else "registered_location")


def config_sources(home, environ=None):
    found = set()
    for t in CATALOG:
        for template in t["configs"]:
            try:
                p, _ = expand_path(template, home, environ)
                if p.is_relative_to(home):
                    found.add(p)
            except (ValueError, KeyError):
                continue
    return sorted(found)


def catalog_report():
    return {"schema_version": 1, "catalog_version": CATALOG_VERSION, "reviewed_on": REVIEWED_ON,
            "entries": CATALOG, "scope_note": "Read-only detection/protection hints, not exhaustive market coverage or certified cleanup support; no cloud accounts are queried."}

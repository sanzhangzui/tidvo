# Install Tidvo for the current AI tool

These instructions are for the AI carrying out the user's installation request.
Handle the mechanics yourself, then give the user a short result and a starting
prompt. Installation does not authorize a disk scan or cleanup.

## Select the destination and runtime

Use the current AI tool's supported local Skills mechanism. Follow the user's
existing skill-location rules and shared-directory links. Install a single skill
named `tidvo`; retain the entire folder, including `scripts/`, `macdev/` and the
pinned `vendor/mole/` runtime. If the current tool or its destination cannot be
identified from context and local configuration, ask only for that missing fact.

Do not overwrite an existing `tidvo` installation or replace a shared Skills
directory/symlink. If Tidvo is already installed and its entry points work,
report that fact. Review any requested update against the existing installation
before replacing files. Preserve previous configuration and recovery records.

Current runtime support is macOS 14+ and Python 3.11+. Check the operating system
and find an existing compatible Python, using its absolute path if `python3`
resolves to an older version. Tidvo has no third-party Python dependencies and
does not require a separate Mole or Node.js installation. If Python is missing,
report the specific requirement; do not silently install or replace runtimes.
Windows support is planned, not implemented. A web-only chat without local file
and command access cannot complete local installation.

## Download the standalone release

Current beta: **v0.2.0-beta.1**. Download both assets into a fresh temporary folder:

- https://github.com/sanzhangzui/tidvo/releases/download/v0.2.0-beta.1/tidvo-0.2.0.tar.gz
- https://github.com/sanzhangzui/tidvo/releases/download/v0.2.0-beta.1/tidvo-0.2.0.tar.gz.sha256

Release information: https://github.com/sanzhangzui/tidvo/releases/tag/v0.2.0-beta.1

Compute the archive's SHA-256 locally and compare it with the checksum file.
Use a safe archive extractor in the temporary folder. Before installing, confirm
that paths stay under `tidvo/`, no links escape that folder, and there is exactly
one `SKILL.md`, at `tidvo/SKILL.md`.

Use the standalone release rather than installing the source tree recursively:
the release omits vendored upstream skill/plugin entry points. After validating
the extracted folder, place it at the selected unused Skills destination.
Download, extraction and checksum details belong in your work, not a list of
commands the user must perform.

## Verify without inspecting the user's data

Using the selected Python interpreter, run the installed entry points:

```text
<python-3.11+> <installed-tidvo>/scripts/tidvo.py --version
<python-3.11+> <installed-tidvo>/scripts/tidvo.py agents --catalog --json
```

The first reports the version; the second lists registered capabilities without
walking Agent data or creating cleanup candidates. Confirm both succeed and the
installed `SKILL.md` declares `name: tidvo`. Read that skill before later use.
Do not run `scan`, a normal `agents` inspection, `plan`, `apply` or `restore` as
an installation check. Do not modify the user's cleanup configuration.

Finish with the installed location, the validation result and this starting prompt:

> 用 Tidvo 只读体检我的 Agent 和开发环境，保留会话、记忆及项目依赖，解释占用最大的内容，并推荐下一步，先不清理。

If the host has not refreshed its Skills list, explain its normal refresh or
new-conversation step. Distinguish successfully copied files from an installation
that is ready to run; state any missing runtime, configuration or host support.

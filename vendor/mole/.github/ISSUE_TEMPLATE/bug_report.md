---
name: CLI Bug Report
about: Report a bug in the Mole command-line tool
title: '[BUG] '
labels: bug
assignees: ''
---

## Before submitting

Run `mo update` to install the latest stable version, then check `mo --version`. Reproduce the problem with that version. If updating itself fails, report that failure and your installed version.

- [ ] I updated and reproduced the problem, or this report explains why I cannot update.

## Describe the bug

Describe what happened. English is preferred so more contributors can help triage.

If you believe the issue may allow unsafe deletion, path validation bypass, privilege boundary bypass, or release/install integrity issues, do not file a public bug report. Report it privately using the contact details in [SECURITY.md](https://github.com/tw93/Mole/blob/main/SECURITY.md).

## Steps to reproduce

1. Run command: `mo ...`
2. ...
3. See error

## Expected behavior

What did you expect to happen instead?

## Debug logs

Run the command with `--debug` and paste the output:

```bash
mo <command> --debug
# Example: mo clean --debug
```

<details>
<summary>Debug output</summary>

```text
Paste debug output here
```

</details>

## Environment

Paste the output of `mo --version` from the version used to reproduce the problem:

```text
Paste mo --version output here
```

## Additional context

Screenshots, error messages, or related details (optional).

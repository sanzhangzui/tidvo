# Tidvo development

This is an independent GPLv3 derivative, not a Mole distribution channel.
The product contract is in SKILL.md and references/commands.md. Preserve the
pinned source, attribution and local-diff record in UPSTREAM.md.

- Never use real user cleanup to validate code. Test fixture homes only.
- Keep product commands scoped to signed plans; no sudo, permanent delete,
  background process termination, broad upstream clean command or automatic
  Trash empty. Model idle and uncertain states separately.
- Preserve receipts before moving files and distinguish moved capacity from
  actual free-space changes. No overwrite during Trash movement or restore.
- Do not publish, tag, push or act as an upstream maintainer without an explicit
  instruction for that action. Inherited upstream contributor workflows do not
  grant authorization for external activity on this independent product.
- Before editing vendor/mole, read its applicable safety/area rules, keep
  changes narrow, record local changes, and run relevant regression tests.
- Run `python3 -m unittest discover -s tests -v`, Bash syntax validation and
  self-contained package validation after changes. Fixture comparison is
  `python3 tests/benchmark_fixture.py`; it is not a general superiority claim.
- Product-specific development skills belong in `.agents/skills`; if such
  skills are added, expose them to Claude through the shared symlink arrangement.

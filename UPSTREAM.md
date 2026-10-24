# Upstream and modifications

This independent GPLv3 derivative incorporates [tw93/Mole](https://github.com/tw93/Mole),
copyright its original authors and contributors. Preserve their attribution.
The derivative is distributed as **Tidvo** (formerly the local Mac Dev Cleanup).
Its Agent-specific behavior and platform status are described in README.md.

- Pinned commit: `db704956981f7c1c6d2b4b51ad13eafd9fef3b79`.
- Source: `vendor/mole/`, including upstream license and regression tests.
- Upstream repository/license: https://github.com/tw93/Mole/blob/main/LICENSE
- The root `LICENSE` is GPLv3. Distribution must include corresponding source
  for this derivative, including the Python layer and bridge, under that license.

Local changes to vendored upstream:

1. `lib/core/log.sh`: allow this product's explicit `MACDEV_MOLE_LOG_DIR` to
   redirect backend logs into its private state directory, instead of sharing
   an installed Mole's logs. Upstream fallback remains unchanged.
2. `lib/core/file_ops.sh`: allow a caller-specified, unique `mac-dev-cleanup-*`
   destination directly within the invoking user's Trash. Reject another parent,
   existing paths and symlinks. This binds write-ahead receipts to the exact move.
   The normal guarded Trash mechanism is retained; no permanent-delete fallback
   is added. Product-only flags also prohibit the inherited cached-sudo probe
   fallback and automatic Trash mode repair. Defaults remain unchanged for
   upstream callers; the adapter always enables these stricter flags and only
   uses same-volume, non-privileged moves.

The new `macdev/` package, agent skill and scripts are this derivative's changes.
Skill archives omit upstream agent/plugin entry points, contributor instruction
files, images and transient test homes, so installing this product cannot also
install Mole's separate published skill. Backend source, licensing and product
tests remain included; the repository retains the pinned upstream source tree.
The upstream broad CLI, owner prune commands, optimization and uninstall are not
called by this product's command interface. Vendored entry points are source for
attribution/review and tests, not supported product commands.

The Python scanner is independently implemented with reference to upstream
project markers and artifact categories; it does not execute the full upstream
purge pipeline, its interactive grouped selection, or its seven-day default
selection heuristic. Mole also discovers nonstandard Home-level project
containers: discovering such a directory is not a product-only advantage.
This product instead preserves project dependency environments by default.
Version 0.1.2's known VS Code, Dia, Feishu/Lark and npm prebuild locations were
reviewed against the pinned `lib/clean/app_caches.sh`, `lib/clean/user.sh` and
`lib/clean/dev.sh` implementations. Python adapters use those exact ownership
layouts while retaining this product's own Trash-only, activity, metadata-index
and uncertainty contracts; the upstream broad cleanup functions are not invoked.

Version 0.2.0's declarative Agent catalog, metadata inventory, path protection and
reference adapters are original Python-layer additions. Their primary references
and evidence limits are recorded in `references/agent-adapters.md` and the catalog.
They add no vendored Mole modifications or Agent-state deletion routines.
The first-public-beta rename changes the skill, display name, primary Python
entry point and archive folder to Tidvo. Original config/state paths, Trash
payload prefixes, backend environment flags and the `macdev` import package stay
compatible; the vendored backend is unchanged by the rename.

When updating: pin the new commit; review the source diff, reapply the two small
adaptations, run relevant upstream safety tests plus the product fixture suite,
and update validation evidence before changing this pin. Never silently track main.

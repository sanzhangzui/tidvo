# Cleanup capacity and coverage (0.2.4)

## Report the full inventory

`cleanup_summary` partitions deduplicated known candidates into five exclusive
buckets: `ready_caches`, `quit_app`, `separate_review`, `protected`, `unverified`.
They report measured allocated bytes, unknown-size/lower-bound counts, owners
and a next action. `ready_caches` still needs a reviewed plan and final guards;
quitting an app does not guarantee every deferred byte becomes eligible.
Outputs and old programs require separate purpose/rollback review.

Human output uses decimal KB/MB/GB and representative rows for long lists; JSON
retains all candidates. Totals include retained data, not savings. Native previews,
Agent inventories and unconfirmed residual inventories are not added to them.

`size_observation` measures readable metadata, including foreign-owned entries,
without reading bodies, following symlinks/mounts or granting move authority.
Hard links are deduplicated. Unreadable/budget gaps stay lower bounds or unknown;
ownership/snapshot failures still prevent plans. No permission repair or sudo.

## New exact user caches

- GeoServices `Resources` and named `.pbd` resource indexes: downloaded map data,
  not saved places or arbitrary Maps app state.
- Named AppleMediaServices resources, Apple Python `Library`/`Users` compiled
  caches, parsecd cache files and mediaanalysisd `Data/tmp/Pissarro`/`TemporaryItems`.
- Xcode `UserData/IB Support/Simulator Devices`: Interface Builder cache, not
  CoreSimulator devices, SDKs, archives or signing material.
- `.android/cache`: SDK metadata, not installed SDK/AVD environments.
- Homebrew cache API metadata, completed hash-named downloads and known root
  archive/JSON files. Incomplete downloads, locks, Cellar/Caskroom stay separate.
- Cargo `registry/cache/<registry>/*.crate`: keep sources, indexes and binaries.
- Ruby `.gem/specs`, Bundler `.bundle/cache/compact_index`: keep installed gems,
  environments and Git source caches.
- PyInstaller `bincache*`: keep project inputs and deliverable builds.

Process/reference, ownership, sensitive-file, exclusion, snapshot and same-volume
Trash guards still apply. Cache-named App Support directories with unknown owners
are `app.unattributed_cache` inventory, without cleanup authority.

`scan --native-preview` invokes only trusted local Homebrew's `cleanup --dry-run`,
with auto-update/analytics/Bootsnap disabled. It requires an already installed,
matching portable Ruby plus Bundler and does not invoke an unbootstrapped/stale
Homebrew runtime. The owner's reported estimate/unit stays a
separate manual-review result; it can overlap caches and is not summed into
candidate capacity. Native cleanup/removal and runtime installation never run.

## Retired Agent extension programs

Agent protection remains the default. A direct `.vscode/extensions` package may
receive the narrow `editor.obsolete_extension` exception only when:

1. `.obsolete` marks that exact folder true, its folder is unregistered, and a
   newer registered folder has the same publisher/name, owned regular metadata
   and a comparable stable version.
2. Bounded metadata/tree inspection finds no known credentials, databases, Agent
   markers or session/memory/history/workspace state. Bodies, extension hooks,
   executables and pruning commands are never read/run. This is known-state
   detection, not certification of every product/layout.
3. Only that exact `known_extension_identity` installed-program root is exempt.
   Custom/environment/resource/shared-skill roots and unknown Agent identities
   continue to protect overlaps. Explicit roots cannot be overwritten by later
   extension-manifest discovery.
4. Registry/replacement/manifest identities, hashes and package fingerprint are
   signed as `extension_context` and rechecked in plan/apply, including after
   occupancy. New registration, persistent state, running old executables/editor,
   references or incomplete evidence prevent movement.

Eligible old programs remain `separate_review`, outside routine cache batches.
Explain losing the old program/rollback copy; sessions/memory/shared resources
are not part of this exception. The current-user observation scope is separately
recorded as `current_user_obsolete_extension`; only context-qualified packages get
it. Unproven legacy packages retain the original strict probe. Other users and
future activity are not certified. Restores use receipts and never overwrite.

## Mole comparisons

`compare_baseline.py` reports matched path capacity, absent paths, matched paths
without measured Tidvo size, unknown baseline sizes and disposition groups. Mole
rounded annotations stay separate from Tidvo measurements. Parent-family matches
do not certify full coverage; timestamps differ and native commands may have no
file rows. This is not an execution benchmark or a guaranteed-space claim.

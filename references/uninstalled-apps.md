# Application installation and residual cleanup (0.2.3)

Before recommending application cleanup, check installation as well as activity.
Native probes inspect standard system/user Applications folders (bounded nested
folders), app Info.plist Bundle IDs and Spotlight Bundle ID matches. App names
also conservatively detect damaged bundles. Renamed, nested and portable matches
prevent uninstalled cleanup. A failed/incomplete search is `unknown`; a negative
search is `not_found` in its stated scope, not proof that every disk was indexed.
Use conversation evidence of uninstallation, rather than treating idle as removed.

The first exact residual adapters are Dia, Google Chrome, Obsidian and Visual
Studio Code. Other owners may have installation observations, but unknown ownership
does not grant residual cleanup. No fuzzy name matching, shared vendor parent,
Group Container, external vault or project dependency is a deletion target.
This is not universal uninstall detection or every app/version certification.

## Conversation workflow

When the user states an app was uninstalled and authorizes its residual removal
(including a standing instruction to directly clean confirmed-uninstalled residuals),
the agent handles `--uninstalled-app APP` internally. Do not make the user learn
flags/IDs or confirm each private database. Show the batch and impact, then proceed
under that existing authorization. Uninstallation alone during an analysis request
does not authorize cleanup. If only the scoped negative search is known, report
possible residuals and resolve the actual uninstall status before removing app data.

Example internal command:

```bash
python3 scripts/tidvo.py scan --uninstalled-app Dia --output NEW_REPORT.json --json
```

`uninstalled_residual_inventory` reports unconfirmed potential residuals separately
from actionable candidates. Its parents can overlap ordinary cache leaves; do not
sum their sizes. They cannot be planned from that inventory. Confirmed residual
candidates use `app.uninstalled_residual` and a signed `residual_context`. Parent
candidates deduplicate nested cache candidates in the actual cleanup batch.

The exact path adapter limits removal to dedicated app paths in Home/Library:
Application Support, Caches, known Logs, bundle-named preferences, HTTPStorages,
WebKit and saved state. It includes private app history, sessions, Cookies and
databases including WAL/SHM/journal. It does not read their contents or databases.
Independent Agent/config/shared-resource protection still applies; nested repos,
Agent markers, certificates and other sensitive non-database files stay protected.

Planning rescans installation and exact ownership/snapshots; apply validates the
fixed adapter, uninstall assertion, current installation and activity/reference
state again, including after the occupancy check. A newly installed/running or
referenced app stops the move. Unreadable metadata, incomplete visibility, path
redirects, foreign ownership and changed payloads remain refusals.

Explicit, owned uninstalled residuals may use the same calibrated current-user
occupancy protocol as reviewed caches, recorded separately as
`current_user_uninstalled_residual`. This permits only the reviewed uninstall
rule, not arbitrary app/Agent data or other users' files. It does not certify
other users' processes or future activity. Restore uses the receipt and occupancy
checks; it never overwrites newly recreated app data after reinstallation.

All removal is a signed, journaled same-volume Trash move with recovery records.
No sudo, permission repairs, app termination, permanent deletion or automatic Trash
empty. After success, report removed residuals; do not recommend reopening the
uninstalled app. Keep moved capacity separate from observed free-space changes.

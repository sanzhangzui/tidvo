"""Known app identities and exact, exclusive user-data paths; no fuzzy deletion."""
import platform
import plistlib
import time
from pathlib import Path

from .safety import Refused


PROFILES = {
    "Dia": {"bundles": ["company.thebrowser.dia"], "names": ["Dia"],
            "support": ["Dia"], "caches": ["Dia", "company.thebrowser.dia"]},
    "Google Chrome": {"bundles": ["com.google.Chrome"], "names": ["Google Chrome"],
                      "support": ["Google/Chrome"], "caches": ["Google/Chrome", "com.google.Chrome"]},
    "Obsidian": {"bundles": ["md.obsidian"], "names": ["Obsidian"],
                 "support": ["obsidian"], "caches": ["md.obsidian"]},
    "Visual Studio Code": {"bundles": ["com.microsoft.VSCode"], "names": ["Visual Studio Code"],
                           "support": ["Code"], "caches": ["com.microsoft.VSCode"], "logs": ["Code"]},
}
RESIDUAL_RULE = "app.uninstalled_residual"


def residual_paths(home, owner):
    profile = PROFILES.get(owner)
    if profile is None:
        return []
    library = Path(home) / "Library"
    paths = [library / "Application Support" / name for name in profile["support"]]
    paths += [library / "Caches" / name for name in profile["caches"]]
    paths += [library / "Logs" / name for name in profile.get("logs", [])]
    for bundle in profile["bundles"]:
        paths += [library / "Preferences" / (bundle + ".plist"),
                  library / "HTTPStorages" / bundle,
                  library / "HTTPStorages" / (bundle + ".binarycookies"),
                  library / "WebKit" / bundle,
                  library / "Saved Application State" / (bundle + ".savedState")]
    return paths


def inspect_installation(owner, home, command, *, app_roots=None):
    """Not-found is scoped evidence, never proof that every volume was indexed."""
    profile = PROFILES.get(owner, {"bundles": [], "names": [owner]})
    roots = list(app_roots) if app_roots is not None else [Path("/Applications"), Path(home) / "Applications", Path("/System/Applications")]
    result = {"status": "unknown", "paths": [], "checked_roots": [str(p) for p in roots],
              "bundle_ids": profile["bundles"], "issues": [], "scope": "standard_app_folders_and_spotlight",
              "absence_is_not_uninstall_proof": True}
    matches, visited = set(), 0
    deadline = time.monotonic() + 8

    def inspect(app):
        if app.stem in profile["names"]:
            matches.add(str(app))  # Even a damaged matching app prevents cleanup.
        info = app / "Contents/Info.plist"
        try:
            if not info.is_file() or info.stat().st_size > 1024 * 1024:
                raise ValueError("invalid_bundle_metadata")
            with info.open("rb") as file:
                data = plistlib.loads(file.read(1024 * 1024 + 1))
            if not isinstance(data, dict):
                raise ValueError("invalid_bundle_metadata")
            if data.get("CFBundleIdentifier") in profile["bundles"]:
                matches.add(str(app))
        except (OSError, ValueError, plistlib.InvalidFileException):
            result["issues"].append("bundle_metadata_unavailable")

    queue = [(Path(root), 0) for root in roots]
    while queue:
        parent, depth = queue.pop()
        visited += 1
        if visited > 4000 or time.monotonic() > deadline:
            result["issues"].append("installation_inventory_budget_exceeded")
            break
        try:
            if not parent.exists():
                if parent.is_symlink():
                    result["issues"].append("application_folder_redirect_unavailable")
                continue
            if parent.is_symlink():
                result["issues"].append("application_folder_redirected")
                continue
            for app in parent.iterdir():
                visited += 1
                if visited > 4000 or time.monotonic() > deadline:
                    result["issues"].append("installation_inventory_budget_exceeded")
                    queue.clear()
                    break
                if app.suffix.lower() == ".app":
                    inspect(app)
                elif app.is_dir() and not app.is_symlink():
                    if depth < 3:
                        queue.append((app, depth + 1))
                    else:
                        result["issues"].append("installation_inventory_depth_exceeded")
        except OSError:
            result["issues"].append("application_folder_unreadable")
    if profile["bundles"] and platform.system() == "Darwin":
        query = " || ".join('kMDItemCFBundleIdentifier == "' + b + '"' for b in profile["bundles"])
        found = command(["/usr/bin/mdfind", query], 8)
        if found is None or found.returncode != 0 or found.stderr.strip():
            result["issues"].append("spotlight_unavailable")
        elif len(found.stdout) > 512 * 1024:
            result["issues"].append("spotlight_output_budget_exceeded")
        else:
            for value in found.stdout.splitlines():
                app = Path(value)
                if not app.is_absolute() or app.suffix.lower() != ".app" or any(ord(c) < 32 for c in value):
                    result["issues"].append("spotlight_output_invalid")
                elif app.exists():
                    inspect(app)
                    if str(app) not in matches:
                        result["issues"].append("spotlight_identity_unverified")
    else:
        result["issues"].append("bundle_search_unsupported")
    result["paths"] = sorted(matches)
    result["issues"] = sorted(set(result["issues"]))
    result["status"] = "installed" if matches else "unknown" if result["issues"] else "not_found"
    return result


def residual_context(owner, asserted):
    return {"app": owner, "bundle_ids": PROFILES[owner]["bundles"],
            "user_confirmed_uninstalled": asserted}


def validate_residual(candidate, home, probe):
    owner = candidate.get("owner")
    if owner not in PROFILES or candidate.get("residual_context") != residual_context(owner, True):
        raise Refused("uninstall_confirmation_or_identity_missing")
    if Path(candidate["path"]) not in residual_paths(home, owner):
        raise Refused("uninstall_residual_path_not_exclusive")
    evidence = probe.installation(owner, refresh=True)
    if evidence["status"] != "not_found":
        raise Refused("application_installed_or_installation_unknown")
    return evidence


def only_database_sensitivity(snapshot):
    # Explicit removal of an uninstalled app includes its private databases.
    # Nested repositories, agent markers, certificates and other sensitive data
    # still need independent review; never broaden ordinary cache rules.
    endings = tuple(ext + suffix for ext in (".db", ".sqlite", ".sqlite3")
                    for suffix in ("", "-wal", "-shm", "-journal"))
    return all(Path(p).name.lower().endswith(endings) for p in snapshot["sensitive"])

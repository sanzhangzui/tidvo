"""Read-only owner previews are never Trash candidates or mutation commands."""
import re
import os
from pathlib import Path


def homebrew_runtime_ready(executable):
    """Do not invoke brew if its startup would bootstrap/upgrade Ruby/Bundler."""
    try:
        repository = Path(executable).resolve(strict=True).parent.parent
        vendor = repository / "Library/Homebrew/vendor"
        version_file = vendor / "portable-ruby-version"
        if version_file.resolve() != version_file or version_file.stat().st_size > 80:
            return False
        value = version_file.read_text().strip()
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:_[0-9]+)?", value):
            return False
        current = vendor / "portable-ruby/current"
        if current.resolve(strict=True) != (vendor / "portable-ruby" / value).resolve(strict=True):
            return False
        return (current / "bin/ruby").is_file() and os.access(current / "bin/ruby", os.X_OK) and (current / "bin/bundle").is_file()
    except (OSError, RuntimeError):
        return False


def brew_preview(command, executable):
    result = command([str(executable), "cleanup", "--dry-run"], 30)
    row = {"tool": "Homebrew", "action": "manual_review", "status": "unavailable",
           "reported_estimate": None, "estimated_bytes": None,
           "next_action": "核对 Homebrew 旧版本和内部工具的影响；Tidvo 不自动执行原生清理",
           "included_in_candidate_totals": False}
    if result is None or result.returncode != 0:
        row["reason"] = "native_preview_failed_or_timed_out"
        return row
    match = re.search(r"would free approximately\s+([0-9.]+\s*[KMGT]?B)", result.stdout, re.I)
    row.update(status="complete", reported_estimate=re.sub(r"\s+", "", match[1]) if match else None,
               item_count=len(re.findall(r"^Would remove:", result.stdout, re.M)),
               reason="owner_dry_run_only; not a plan or guaranteed disk savings")
    if result.stderr.strip():
        row.update(status="partial", reason="native_preview_has_diagnostics")
    return row

#!/usr/bin/env python3
"""Read-only comparison of product discovery and pinned Mole purge discovery.

Only synthetic project trees are inspected. No real HOME, deletion, owner prune,
Mole main/clean/uninstall/optimize command, or permission elevation is involved.
This is coverage evidence for this small fixture, not a general benchmark claim.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from macdev.scanner import Scanner
from macdev.safety import tree_snapshot
from macdev.probes import NativeProbe


class IdleFixtureProbe(NativeProbe):
    def __init__(self, home):
        self.home = home
        self.references = set()
        self.config_paths = set()
        self.reference_status = "complete"
        self.refresh()
    def refresh(self):
        self.rows = []
        self._references()
    def owner_cache_paths(self): return []
    def idle(self, path, *, rule_id=None): return "idle"


def benchmark():
    with tempfile.TemporaryDirectory(prefix="macdev-comparison-") as name:
        home = Path(name).resolve() / "home"
        home.mkdir(mode=0o700)
        # The scoped upstream helper expects its CLI's scratch directory.
        (home / ".cache/mole").mkdir(parents=True)
        projects = home / "unusual-workspace"
        payloads = {
            "frontend/package.json": json.dumps({"name": "fixture", "scripts": {"build": "fixture"}}),
            "frontend/node_modules/fixture/index.js": "module.exports = 1",
            "frontend/dist/app.js": "fixture output",
            "python/pyproject.toml": '[project]\nname="fixture"\nversion="0.1"\n',
            "python/requirements.txt": "",
            "python/.venv/pyvenv.cfg": "version = 3.11",
            "python/.venv/lib/fixture.py": "# fixture dependency",
            "python/__pycache__/fixture.cpython-311.pyc": "synthetic bytecode",
            "rust/Cargo.toml": '[package]\nname="fixture"\nversion="0.1.0"\n',
            "rust/target/debug/fixture": "synthetic executable",
            "frontend/src/keep.js": "user source stays",
        }
        for relative, text in payloads.items():
            p = projects / relative
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        for name, package in [("unused-tool", "fixture-tool"), ("configured-tool", "fixture-mcp")]:
            p = home / ".npm/_npx" / name / "package.json"
            p.parent.mkdir(parents=True)
            p.write_text(json.dumps({"dependencies": {package: "1.0.0"}}))
        config = home / ".cursor/mcp.json"
        config.parent.mkdir()
        config.write_text(json.dumps({"mcpServers": {"fixture": {"command": "npx", "args": ["fixture-mcp"]}}}))
        before = tree_snapshot(projects)
        with patch.dict(os.environ, {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}, clear=True):
            report = Scanner(home=home, roots=[projects], probe=IdleFixtureProbe(home)).scan()
        output = home / "mole-purge-discovery.txt"
        npm_output = home / "mole-npx-preview.txt"
        env = dict(HOME=str(home), PATH="/usr/bin:/bin:/usr/sbin:/sbin", MOLE_TEST_NO_AUTH="1", MOLE_DRY_RUN="1", NO_COLOR="1", DRY_RUN="true")
        shell = 'set -euo pipefail; source "$1/bin/clean.sh"; source "$1/lib/clean/project.sh"; EXPORT_LIST_FILE="$4"; clean_dev_npm; scan_purge_targets "$2" "$3"'
        result = subprocess.run(["/bin/bash", "--noprofile", "--norc", "-c", shell, "fixture", str(ROOT / "vendor/mole"), str(projects), str(output), str(npm_output)],
                                env=env, capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise RuntimeError("upstream fixture discovery failed: " + str(result.returncode) + ": " + result.stderr[-1500:] + result.stdout[-500:])
        baseline = output.read_text().splitlines()
        baseline += [line.split("  # ", 1)[0] for line in npm_output.read_text().splitlines() if line.startswith("/")] if npm_output.exists() else []
        baseline_text = "\n".join(p + "  # size unknown" for p in baseline if p.startswith("/"))
        spec = importlib.util.spec_from_file_location("comparison", ROOT / "scripts/compare_baseline.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        comparison = module.compare(report, baseline_text)
        if before != tree_snapshot(projects):
            raise RuntimeError("fixture payload changed during read-only comparison")
        def relative(p): return str(Path(p).relative_to(home))
        return {"fixture": "three synthetic projects and two npx installs, one configured MCP", "payload_unchanged": True,
                "upstream_commit": "db704956981f7c1c6d2b4b51ad13eafd9fef3b79",
                "baseline_scope": "Mole scan_purge_targets discovery plus clean_dev_npm dry-run; not full CLI or execution eligibility",
                "activity_model": "product evidence uses a synthetic idle probe; not an occupancy benchmark",
                "product_candidates": [{"path": relative(x["path"]), "rule_id": x["rule_id"], "action": x["action"]} for x in report["candidates"]],
                "upstream_paths": [relative(p) for p in baseline if p.startswith("/")],
                "overlapping_product_candidates": comparison["overlapping_product_candidates"],
                "product_only_paths": [relative(x["path"]) for x in comparison["product_only"]],
                "baseline_only_paths": [relative(p) for p in comparison["baseline_only_paths"]],
                "notes": comparison["notes"]}


if __name__ == "__main__":
    print(json.dumps(benchmark(), indent=2))

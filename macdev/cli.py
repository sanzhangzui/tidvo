import argparse
import json
import os
import platform
import sys
from pathlib import Path

from . import __version__
from .engine import apply, make_plan, restore
from .display import render
from .agent_catalog import catalog_report
from .app_installation import PROFILES
from .safety import Refused
from .scanner import Scanner
from .state import State


def parser():
    p = argparse.ArgumentParser(description="Tidvo: disk cleanup with extra protection for AI Agent and development data. macOS beta; Windows planned. Trash only, never sudo or permanent delete.")
    p.add_argument("--version", action="version", version=__version__)
    commands = p.add_subparsers(dest="command", required=True)
    s = commands.add_parser("scan", help="Read-only discovery; does not create product state")
    s.add_argument("--root", action="append", default=[])
    s.add_argument("--exclude", action="append", default=[])
    s.add_argument("--budget", type=int, default=120)
    s.add_argument("--json", action="store_true", help="Machine-readable JSON instead of the terminal summary")
    s.add_argument("--output", type=Path)
    s.add_argument("--uninstalled-app", action="append", default=[], choices=sorted(PROFILES),
                   help="Acknowledge the user confirmed this app was uninstalled and its exclusive residual data may be removed; still requires a reviewed signed plan")
    s = commands.add_parser("agents", help="Metadata-only Agent inventory and protection; never creates cleanup candidates")
    s.add_argument("--root", action="append", default=[])
    s.add_argument("--exclude", action="append", default=[])
    s.add_argument("--budget", type=int, default=120)
    s.add_argument("--json", action="store_true")
    s.add_argument("--output", type=Path)
    s.add_argument("--catalog", action="store_true", help="List registered detection/protection capabilities, not installed tools")
    s = commands.add_parser("plan", help="Revalidate explicitly selected candidate IDs")
    s.add_argument("--scan", type=Path, required=True)
    s.add_argument("--json", action="store_true")
    selection = s.add_mutually_exclusive_group(required=True)
    selection.add_argument("--ids", nargs="+")
    selection.add_argument("--all-actionable", action="store_true")
    for name, key in [("apply", "plan"), ("restore", "run")]:
        s = commands.add_parser(name)
        s.add_argument("--" + key, required=True, help="ID returned by plan/history")
        s.add_argument("--confirmed", action="store_true", help="Acknowledge prior review of the exact plan/run")
        s.add_argument("--json", action="store_true")
    s = commands.add_parser("history")
    s.add_argument("--json", action="store_true")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        # Product configuration only supplies scan scope, never shell commands.
        home = Path.home().resolve()
        config_path = home / ".config/mac-dev-cleanup/config.json"
        config = {}
        if config_path.exists():
            if config_path.resolve() != config_path or config_path.stat().st_size > 1024 * 1024:
                raise Refused("untrusted_configuration_path")
            config = json.loads(config_path.read_text())
            if not isinstance(config, dict) or any(not isinstance(config.get(k, []), list) or any(not isinstance(x, str) for x in config.get(k, [])) for k in ["roots", "excludes"]):
                raise Refused("configuration_roots_and_excludes_must_be_string_lists")
        if args.command in ["scan", "agents"]:
            if not 1 <= args.budget <= 600:
                raise Refused("budget_must_be_between_1_and_600_seconds")
            if args.command == "agents" and args.catalog:
                result = catalog_report()
            else:
                scanner = Scanner(home=home, roots=args.root or config.get("roots", []),
                                  excludes=config.get("excludes", []) + args.exclude, budget=args.budget,
                                  uninstalled_apps=getattr(args, "uninstalled_app", []))
                if args.command == "scan":
                    result = scanner.scan()
                else:
                    try:
                        scanner.projects(discover_only=True)
                    except (OSError, Refused) as exc:
                        scanner.issues.append({"reason": str(exc) if isinstance(exc, Refused) else type(exc).__name__})
                    result = scanner.agent_policy.audit(deadline=scanner.deadline, probe=scanner.probe)
                    result["projects_discovered"] = len(scanner.project_roots)
                    result["issues"] = result["issues"] + scanner.issues
                    if result["issues"]:
                        result["scan_status"] = "partial"
        else:
            if args.command == "history" and not (home / ".local/state/mac-dev-cleanup").exists():
                print(json.dumps({"runs": []}) if args.json else "暂无清理记录。")
                return 0
            if args.command in ["apply", "restore"]:
                if platform.system() != "Darwin" or int(platform.mac_ver()[0].split(".")[0] or 0) < 14:
                    raise Refused("mutation_requires_macos_14_or_later")
                if os.geteuid() == 0:
                    raise Refused("run_as_normal_user_without_sudo")
            state = State(home)
            if args.command == "plan":
                report = json.loads(args.scan.read_text())
                ids = args.ids if args.ids is not None else [x["id"] for x in report["candidates"] if x["action"] == "trash"]
                result = make_plan(report, ids, state)
            elif args.command == "apply":
                result = apply(args.plan, state, confirmed=args.confirmed)
            elif args.command == "restore":
                result = restore(args.run, state, confirmed=args.confirmed)
            else:
                result = {"runs": state.history()}
        output = json.dumps(result, ensure_ascii=False, indent=2)
        if getattr(args, "output", None):
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(output + "\n")
        print(output if args.json else render(args.command, result, report_path=getattr(args, "output", None)))
        return 0
    except (Refused, OSError, ValueError, KeyError, TypeError) as exc:
        reason = str(exc) if isinstance(exc, Refused) else type(exc).__name__
        print(json.dumps({"error": reason, "changed": "consult durable receipts if an operation was in progress"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

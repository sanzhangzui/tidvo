#!/usr/bin/env python3
"""Compare existing read-only artifacts, not destructive head-to-head runs."""
import argparse
import json
from pathlib import Path


def compare(report, text):
    baseline = sorted({line.rpartition("  # ")[0] for line in text.splitlines() if line.startswith("/")})
    product = report["candidates"]
    def overlaps(one, two):
        a, b = Path(one), Path(two)
        return a == b or a.is_relative_to(b) or b.is_relative_to(a)
    matched = [x for x in product if any(overlaps(x["path"], p) for p in baseline)]
    product_only = [x for x in product if not any(overlaps(x["path"], p) for p in baseline)]
    baseline_only = [p for p in baseline if not any(overlaps(x["path"], p) for x in product)]
    return {"schema_version": 1, "product_scan_status": report["scan_status"],
            "product_scan_duration_seconds": report.get("scan_duration_seconds"),
            "overlapping_product_candidates": len(matched), "product_only": product_only,
            "baseline_only_paths": baseline_only,
            "notes": ["path overlap is not proof of equal rules, completeness, or reclaimable space",
                      "product-only entries are not a measured GB advantage; inspect evidence and scope",
                      "this artifact-overlap calculation never invokes a Mole command, applies a plan, or measures relative execution speed"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--mole-list", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(json.loads(args.scan.read_text()), args.mole_list.read_text()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

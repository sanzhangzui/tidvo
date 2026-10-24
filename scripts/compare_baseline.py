#!/usr/bin/env python3
"""Compare existing read-only artifacts, not destructive head-to-head runs."""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from macdev.cleanup_summary import disposition


def compare(report, text):
    baseline = sorted({line.rpartition("  # ")[0] for line in text.splitlines() if line.startswith("/")})
    product = report["candidates"]
    def overlaps(one, two):
        a, b = Path(one), Path(two)
        return a == b or a.is_relative_to(b) or b.is_relative_to(a)
    matched = [x for x in product if any(overlaps(x["path"], p) for p in baseline)]
    product_only = [x for x in product if not any(overlaps(x["path"], p) for p in baseline)]
    baseline_only = [p for p in baseline if not any(overlaps(x["path"], p) for x in product)]
    coverage = {"mole_known_annotated_bytes": 0, "matching_path_annotated_bytes": 0,
                "no_matching_path_annotated_bytes": 0, "matching_path_without_measured_size_bytes": 0,
                "mole_unknown_size_count": 0, "by_disposition": {}, "parent_family_match_count": 0}
    seen=set()
    units={"B":1,"KB":1000,"MB":1000000,"GB":1000000000,"TB":1000000000000}
    for line in text.splitlines():
        if not line.startswith('/'):
            continue
        path,separator,note=line.rpartition('  # ')
        if not separator or path in seen or 'counted under' in note:
            continue
        seen.add(path)
        size=re.match(r'([0-9.]+)([KMGT]?B)',note)
        if not size:
            coverage['mole_unknown_size_count']+=1
            continue
        value=round(float(size[1])*units[size[2]])
        coverage['mole_known_annotated_bytes']+=value
        matched=[c for c in product if overlaps(c['path'],path)]
        if not matched:
            coverage['no_matching_path_annotated_bytes']+=value
            continue
        coverage['matching_path_annotated_bytes']+=value
        if not any(c.get('allocated_bytes') is not None for c in matched):
            coverage['matching_path_without_measured_size_bytes']+=value
        if not any(c['path']==path for c in matched) and any(Path(c['path']).is_relative_to(Path(path)) for c in matched):
            coverage['parent_family_match_count']+=1
        dispositions={c.get('disposition') or disposition(c) for c in matched}
        key=next(iter(dispositions)) if len(dispositions)==1 else 'mixed'
        coverage['by_disposition'][key]=coverage['by_disposition'].get(key,0)+value
    return {"schema_version": 1, "product_scan_status": report["scan_status"],
            "product_scan_duration_seconds": report.get("scan_duration_seconds"),
            "overlapping_product_candidates": len(matched), "product_only": product_only,
            "baseline_only_paths": baseline_only,
            "coverage_summary": coverage,
            "notes": ["path overlap is not proof of equal rules, completeness, or reclaimable space",
                      "Mole annotated rounded sizes are grouped separately from Tidvo measured capacity; scans may be from different times",
                      "a parent-family match does not certify full coverage of the baseline parent; native commands may have no path rows",
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

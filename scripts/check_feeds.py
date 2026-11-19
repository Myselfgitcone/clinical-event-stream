"""Fail the build if the published feeds are not what the page and the portfolio
board expect. Run after `ces run`; takes the two file paths."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_SUMMARY = ["generated_at", "synthetic", "cohorts", "volumes", "deid", "condition_pairs", "care_gaps", "dbt"]
REQUIRED_VOLUMES = ["patients", "encounters", "conditions", "observations", "quarantine"]
REQUIRED_WEEKLY = ["week_start", "patients", "encounters", "quarantine"]


def main(summary_path: str, weekly_path: str) -> int:
    problems: list[str] = []
    summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    for k in REQUIRED_SUMMARY:
        if k not in summary:
            problems.append(f"summary.json missing {k}")
    for k in REQUIRED_VOLUMES:
        if k not in summary.get("volumes", {}):
            problems.append(f"summary.volumes missing {k}")
    if summary.get("synthetic") is not True:
        problems.append("summary.synthetic must be true")
    if summary.get("volumes", {}).get("patients", 0) <= 0:
        problems.append("no patients in the warehouse")
    dbt = summary.get("dbt", {})
    if dbt.get("tests", 0) == 0 or dbt.get("failures"):
        problems.append(f"dbt tests did not pass cleanly: {dbt}")
    weekly = json.loads(Path(weekly_path).read_text(encoding="utf-8"))
    if not isinstance(weekly, list) or not weekly:
        problems.append("weekly.json is not a non-empty list")
    else:
        for k in REQUIRED_WEEKLY:
            if k not in weekly[-1]:
                problems.append(f"weekly.json point missing {k}")
        weeks = [p.get("week_start") for p in weekly]
        if weeks != sorted(set(weeks)):
            problems.append("weekly.json is not sorted and unique by week_start")
    # nothing identifying may be in the public feeds
    blob = json.dumps(summary) + json.dumps(weekly)
    for needle in ("ssn", "family_name", "given_name", "address_line", "postal_code"):
        if f'"{needle}"' in blob:
            problems.append(f"feed contains a column named {needle}")
    if problems:
        print("\n".join(problems))
        return 1
    print(f"feeds ok: {summary['volumes']['patients']} patients, {len(weekly)} week(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))

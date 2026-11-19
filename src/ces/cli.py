"""``ces`` command line: one verb per stage, and ``run`` for all of them."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from ces import azure_landing, export, ingest, silver, synthea, warehouse
from ces.config import settings


def log(msg: str) -> None:
    print(msg, flush=True)


def _cohort_arg(args) -> synthea.Cohort:
    if args.weekly:
        return synthea.cohort_for_week(date.today(), args.patients)
    seed = args.seed
    ref = date.fromisoformat(args.reference_date) if args.reference_date else date(2026, 11, 18)
    return synthea.Cohort(seed=seed, patients=args.patients, reference_date=ref)


def cmd_generate(args) -> int:
    cfg = settings()
    synthea.generate(cfg, _cohort_arg(args), log)
    return 0


def _cohorts(cfg, args) -> list[str]:
    if getattr(args, "cohort", None):
        return [args.cohort]
    found = ingest.list_cohorts(cfg)
    if not found:
        log("no cohorts under data/raw; run `ces generate` first")
        sys.exit(2)
    return found


def cmd_ingest(args) -> int:
    cfg = settings()
    for cid in _cohorts(cfg, args):
        ingest.ingest_cohort(cfg, cid, log)
    return 0


def cmd_deid(args) -> int:
    cfg = settings()
    for cid in _cohorts(cfg, args):
        silver.build_silver(cfg, cid, log)
    return 0


def cmd_transform(args) -> int:
    cfg = settings()
    summary = warehouse.run_dbt(cfg, ["build"], log)
    warehouse.export_gold(cfg, log)
    (cfg.data_dir / "warehouse" / "dbt_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return 0


def cmd_export(args) -> int:
    cfg = settings()
    p = cfg.data_dir / "warehouse" / "dbt_summary.json"
    dbt_summary = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    export.export_site(cfg, dbt_summary, ingest.list_cohorts(cfg), log, extend_series=not args.no_extend)
    return 0


def cmd_land(args) -> int:
    cfg = settings()
    azure_landing.land(cfg, log=log)
    return 0


def cmd_run(args) -> int:
    """Everything, in order: generate, ingest, de-identify, transform, export, land."""
    cfg = settings()
    cohort = _cohort_arg(args)
    synthea.generate(cfg, cohort, log)
    cohorts = [cohort.id] if args.only_this_cohort else ingest.list_cohorts(cfg)
    for cid in cohorts:
        if not ingest.bronze_meta_path(cfg, cid).exists() or args.force:
            ingest.ingest_cohort(cfg, cid, log)
        else:
            log(f"bronze {cid} already ingested, skipping (use --force to redo)")
        silver.build_silver(cfg, cid, log)
    dbt_summary = warehouse.run_dbt(cfg, ["build"], log)
    warehouse.export_gold(cfg, log)
    (cfg.data_dir / "warehouse" / "dbt_summary.json").write_text(json.dumps(dbt_summary, indent=1), encoding="utf-8")
    export.export_site(cfg, dbt_summary, cohorts, log, extend_series=not args.no_extend)
    azure_landing.land(cfg, log=log)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ces", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def cohort_opts(sp):
        sp.add_argument("--patients", type=int, default=2000, help="alive patients to generate (default 2000)")
        sp.add_argument("--seed", type=int, default=20261118, help="Synthea population + clinician seed")
        sp.add_argument("--reference-date", help="YYYY-MM-DD Synthea treats as today (default 2026-11-18)")
        sp.add_argument("--weekly", action="store_true", help="seed and reference date from the current ISO week")

    g = sub.add_parser("generate", help="run Synthea for one cohort")
    cohort_opts(g)
    g.set_defaults(fn=cmd_generate)

    for name, fn, help_ in (
        ("ingest", cmd_ingest, "bundles to bronze + quarantine"),
        ("deid", cmd_deid, "bronze to de-identified silver"),
    ):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--cohort", help="one cohort id, default all under data/raw")
        sp.set_defaults(fn=fn)

    t = sub.add_parser("transform", help="dbt build on DuckDB, then export gold parquet")
    t.set_defaults(fn=cmd_transform)

    e = sub.add_parser("export", help="write site/data/summary.json and weekly.json")
    e.add_argument("--no-extend", action="store_true", help="do not fetch the published series first")
    e.set_defaults(fn=cmd_export)

    land = sub.add_parser("land", help="upload layers to ADLS Gen2 (CES_TARGET=azure)")
    land.set_defaults(fn=cmd_land)

    r = sub.add_parser("run", help="generate, ingest, de-identify, transform, export, land")
    cohort_opts(r)
    r.add_argument("--force", action="store_true", help="re-ingest cohorts that already have bronze")
    r.add_argument("--only-this-cohort", action="store_true", help="ignore other cohorts under data/raw")
    r.add_argument("--no-extend", action="store_true", help="do not fetch the published series first")
    r.set_defaults(fn=cmd_run)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)

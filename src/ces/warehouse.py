"""Run the dbt project against DuckDB and export the gold layer as parquet."""

from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb

from ces.config import Settings

GOLD_TABLES = [
    "dim_patient",
    "dim_date",
    "dim_condition",
    "dim_medication",
    "dim_provider",
    "dim_payer",
    "fct_encounter",
    "fct_condition",
    "fct_medication_request",
    "fct_observation",
    "fct_procedure",
    "fct_immunization",
    "mart_condition_pairs",
    "mart_care_gaps",
    "rpt_quarantine",
    "rpt_deid_audit",
    "rpt_k_anonymity",
]


def dbt_env(cfg: Settings) -> dict[str, str]:
    env = dict(os.environ)
    env["CES_WAREHOUSE_PATH"] = cfg.warehouse_path.as_posix()
    env["CES_SILVER_DIR"] = cfg.silver_dir.as_posix()
    env["CES_BRONZE_DIR"] = cfg.bronze_dir.as_posix()
    env["DBT_PROFILES_DIR"] = cfg.transform_dir.as_posix()
    return env


def run_dbt(cfg: Settings, args: list[str], log=print) -> dict:
    """Invoke dbt in-process. Returns a summary of the run results."""
    from dbt.cli.main import dbtRunner

    cfg.warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    env = dbt_env(cfg)
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        res = dbtRunner().invoke(
            [*args, "--project-dir", cfg.transform_dir.as_posix(), "--profiles-dir", cfg.transform_dir.as_posix()]
        )
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    # dbt keeps its DuckDB connection open on the adapter; release it so the
    # export below can open the same file.
    from dbt.adapters.factory import reset_adapters

    reset_adapters()
    if res.exception:
        raise res.exception
    summary = {
        "success": bool(res.success),
        "models": 0,
        "tests": 0,
        "tests_passed": 0,
        "tests_warned": 0,
        "failures": [],
        "warnings": [],
    }
    results = getattr(res.result, "results", None) or []
    for r in results:
        node = r.node
        status = str(r.status)
        if node.resource_type == "model":
            summary["models"] += 1
        elif node.resource_type == "test":
            summary["tests"] += 1
            if status == "pass":
                summary["tests_passed"] += 1
            elif status == "warn":
                summary["tests_warned"] += 1
                summary["warnings"].append(node.name)
        if status in ("error", "fail"):
            summary["failures"].append(f"{node.resource_type} {node.name}: {r.message}")
    if not res.success:
        raise RuntimeError("dbt failed: " + "; ".join(summary["failures"][:5]))
    log(
        f"dbt: {summary['models']} models, {summary['tests_passed']}/{summary['tests']} tests passed"
        + (f", {summary['tests_warned']} warned" if summary["tests_warned"] else "")
    )
    return summary


def export_gold(cfg: Settings, log=print) -> dict[str, int]:
    """Copy every gold table to parquet under data/gold so the Azure landing and
    anyone without dbt can read the warehouse."""
    cfg.gold_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with duckdb.connect(str(cfg.warehouse_path)) as con:
        for t in GOLD_TABLES:
            out = cfg.gold_dir / f"{t}.parquet"
            con.execute(f"copy (select * from gold.{t}) to '{out.as_posix()}' (format parquet, compression zstd)")
            counts[t] = con.execute(f"select count(*) from gold.{t}").fetchone()[0]
    (cfg.gold_dir / "_tables.json").write_text(json.dumps(counts, indent=1), encoding="utf-8")
    log(f"gold: {len(counts)} tables exported to {cfg.gold_dir}")
    return counts


def warehouse_size_bytes(cfg: Settings) -> int:
    p: Path = cfg.warehouse_path
    return p.stat().st_size if p.exists() else 0

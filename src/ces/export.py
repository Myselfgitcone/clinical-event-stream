"""Publish what the warehouse knows as two JSON feeds the status page and the
portfolio board read: ``summary.json`` (now) and ``weekly.json`` (the series).

The weekly series lives only in the published feed. A run fetches the current
series, upserts its own week and writes it back, so the page keeps a history
without the repo or the runner having to keep state.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb

from ces import __version__
from ces.config import Settings
from ces.warehouse import warehouse_size_bytes


def _rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def _one(con: duckdb.DuckDBPyConnection, sql: str) -> dict[str, Any]:
    rows = _rows(con, sql)
    return rows[0] if rows else {}


def _json_ready(v: Any) -> Any:
    if isinstance(v, datetime | date):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _json_ready(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_json_ready(x) for x in v]
    return v


def build_summary(cfg: Settings, dbt_summary: dict | None, cohort_ids: list[str], generated_at: datetime) -> dict:
    with duckdb.connect(str(cfg.warehouse_path)) as con:
        volumes = _one(
            con,
            """
            select
              (select count(*) from gold.dim_patient where is_current)        as patients,
              (select count(*) from gold.fct_encounter)                        as encounters,
              (select count(*) from gold.fct_condition)                        as conditions,
              (select count(*) from gold.fct_observation)                      as observations,
              (select count(*) from gold.fct_medication_request)               as medication_requests,
              (select count(*) from gold.fct_procedure)                        as procedures,
              (select count(*) from gold.fct_immunization)                     as immunizations,
              (select coalesce(sum(rows), 0) from gold.rpt_quarantine)         as quarantine
            """,
        )
        quarantine_reasons = _rows(
            con,
            "select contract, reason, sum(rows) as rows from gold.rpt_quarantine "
            "group by 1, 2 order by 3 desc limit 10",
        )
        deid = _rows(con, "select * from gold.rpt_deid_audit order by table_name")
        k_anon = _one(con, "select * from gold.rpt_k_anonymity")
        pairs = _rows(
            con,
            """
            select condition_a, condition_b, patients_with_both, lift, share_of_patients
            from gold.mart_condition_pairs order by patients_with_both desc limit 8
            """,
        )
        gaps_overall = _one(
            con,
            """
            select
              sum(diabetics)                                  as diabetics,
              sum(statin_eligible)                            as statin_eligible,
              sum(statin_within_year)                         as statin_within_year,
              sum(a1c_within_90d)                             as a1c_within_90d
            from gold.mart_care_gaps
            """,
        )
        gaps_by_band = _rows(
            con,
            """
            select age_band,
                   sum(diabetics) as diabetics,
                   sum(statin_eligible) as statin_eligible,
                   sum(statin_within_year) as statin_within_year,
                   sum(a1c_within_90d) as a1c_within_90d
            from gold.mart_care_gaps group by 1 order by 1
            """,
        )
        gaps_by_payer = _rows(
            con,
            """
            select payer_type,
                   sum(diabetics) as diabetics,
                   sum(statin_eligible) as statin_eligible,
                   sum(statin_within_year) as statin_within_year,
                   sum(a1c_within_90d) as a1c_within_90d
            from gold.mart_care_gaps group by 1 order by 2 desc
            """,
        )
        encounter_span = _one(
            con,
            "select min(period_start) as first_encounter, max(period_start) as last_encounter from gold.fct_encounter",
        )

    def share(num: Any, den: Any) -> float | None:
        return round(num / den, 4) if den else None

    g = gaps_overall
    care_gaps = {
        "diabetics": g.get("diabetics") or 0,
        "statin_eligible": g.get("statin_eligible") or 0,
        "statin_within_year": g.get("statin_within_year") or 0,
        "statin_within_year_share": share(g.get("statin_within_year") or 0, g.get("statin_eligible") or 0),
        "a1c_within_90d": g.get("a1c_within_90d") or 0,
        "a1c_within_90d_share": share(g.get("a1c_within_90d") or 0, g.get("diabetics") or 0),
        "by_age_band": [
            {
                **r,
                "statin_share": share(r["statin_within_year"], r["statin_eligible"]),
                "a1c_share": share(r["a1c_within_90d"], r["diabetics"]),
            }
            for r in gaps_by_band
        ],
        "by_payer_type": [
            {
                **r,
                "statin_share": share(r["statin_within_year"], r["statin_eligible"]),
                "a1c_share": share(r["a1c_within_90d"], r["diabetics"]),
            }
            for r in gaps_by_payer
        ],
    }
    bronze_meta = []
    skipped: dict[str, int] = {}
    for cid in cohort_ids:
        p = cfg.bronze_dir / "_meta" / f"{cid}.json"
        if p.exists():
            m = json.loads(p.read_text(encoding="utf-8"))
            bronze_meta.append({"cohort_id": cid, "bundles": m["bundles"], "seconds": m["seconds"]})
            for k, v in m.get("skipped_resource_types", {}).items():
                skipped[k] = skipped.get(k, 0) + v
    return _json_ready(
        {
            "generated_at": generated_at.isoformat(),
            "version": __version__,
            "synthetic": True,
            "note": "Every patient is synthetic (Synthea). "
            "De-identification is demonstrated on data that was never real.",
            "cohorts": bronze_meta,
            "volumes": volumes,
            "quarantine_reasons": quarantine_reasons,
            "deid": {"tables": deid, "k_anonymity": k_anon},
            "condition_pairs": pairs,
            "care_gaps": care_gaps,
            "encounter_span": encounter_span,
            "skipped_resource_types": skipped,
            "dbt": dbt_summary or {},
            "warehouse_bytes": warehouse_size_bytes(cfg),
            "portfolio_url": "https://jagadish-butukuri.vercel.app",
        }
    )


def fetch_published_weekly(base_url: str, timeout: float = 10.0) -> list[dict]:
    url = base_url.rstrip("/") + "/data/weekly.json"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310 - fixed https base
            data = json.loads(r.read().decode("utf-8"))
        return data if isinstance(data, list) else []
    except (urllib.error.URLError, ValueError, TimeoutError):
        return []


def week_start(day: date) -> date:
    y, w, _ = day.isocalendar()
    return date.fromisocalendar(y, w, 1)


def weekly_point(summary: dict, run_day: date, cohort_ids: list[str]) -> dict:
    v = summary["volumes"]
    cg = summary["care_gaps"]
    k = summary["deid"]["k_anonymity"] or {}
    top = (summary.get("condition_pairs") or [{}])[0]
    return {
        "week_start": week_start(run_day).isoformat(),
        "generated_at": summary["generated_at"],
        "cohorts": cohort_ids,
        "patients": v.get("patients", 0),
        "encounters": v.get("encounters", 0),
        "conditions": v.get("conditions", 0),
        "observations": v.get("observations", 0),
        "quarantine": v.get("quarantine", 0),
        "statin_within_year_share": cg.get("statin_within_year_share"),
        "a1c_within_90d_share": cg.get("a1c_within_90d_share"),
        "k_min_group": k.get("min_group_size"),
        "share_in_groups_under_5": k.get("share_in_groups_under_5"),
        "top_pair": f"{top.get('condition_a')} + {top.get('condition_b')}" if top else None,
        "tests_passed": (summary.get("dbt") or {}).get("tests_passed"),
        "tests": (summary.get("dbt") or {}).get("tests"),
    }


def merge_weekly(existing: list[dict], point: dict) -> list[dict]:
    by_week = {p["week_start"]: p for p in existing if isinstance(p, dict) and p.get("week_start")}
    by_week[point["week_start"]] = point
    return [by_week[k] for k in sorted(by_week)]


def write_site_data(cfg: Settings, summary: dict, weekly: list[dict], out_dir: Path | None = None) -> Path:
    out = out_dir or (cfg.site_dir / "data")
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    (out / "weekly.json").write_text(json.dumps(weekly, indent=1), encoding="utf-8")
    return out


def export_site(
    cfg: Settings, dbt_summary: dict | None, cohort_ids: list[str], log=print, extend_series: bool = True
) -> dict:
    now = datetime.now(UTC)
    summary = build_summary(cfg, dbt_summary, cohort_ids, now)
    existing = fetch_published_weekly(cfg.published_base_url) if extend_series else []
    weekly = merge_weekly(existing, weekly_point(summary, now.date(), cohort_ids))
    out = write_site_data(cfg, summary, weekly)
    log(f"site: summary.json + weekly.json ({len(weekly)} weeks) in {out}")
    return summary

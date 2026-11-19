"""Bronze to silver: the only reader of bronze, and the only writer of silver."""

from __future__ import annotations

import json
import time
from datetime import UTC, date, datetime

import pyarrow as pa

from ces.config import Settings
from ces.contracts import Contract, load_contracts
from ces.deid import DEID_VERSION, Audit, Deidentifier, silver_schema
from ces.parquet import ParquetSink, read_rows

AUDIT_SCHEMA = pa.schema(
    [
        pa.field("cohort_id", pa.string()),
        pa.field("table_name", pa.string()),
        pa.field("reference_date", pa.date32()),
        pa.field("built_at", pa.timestamp("us", tz="UTC")),
        pa.field("deid_version", pa.int32()),
        pa.field("rows", pa.int64()),
        pa.field("dropped_fields", pa.string()),
        pa.field("pseudonymised_values", pa.int64()),
        pa.field("shifted_dates", pa.int64()),
        pa.field("zip3_truncated", pa.int64()),
        pa.field("zip3_restricted_to_000", pa.int64()),
        pa.field("age_over_89_banded", pa.int64()),
        pa.field("free_text_sweeps", pa.int64()),
    ]
)


def cohort_reference_date(cfg: Settings, cohort_id: str) -> date:
    marker = cfg.raw_dir / cohort_id / "cohort.json"
    if marker.exists():
        return date.fromisoformat(json.loads(marker.read_text(encoding="utf-8"))["reference_date"])
    return date.today()


def build_silver(cfg: Settings, cohort_id: str, log=print, contracts: dict[str, Contract] | None = None) -> dict:
    contracts = contracts or load_contracts()
    started = time.monotonic()
    deid = Deidentifier(cfg.deid_salt, cohort_reference_date(cfg, cohort_id))
    audits: dict[str, Audit] = {}
    for name, contract in contracts.items():
        src = cfg.bronze_dir / name / f"{cohort_id}.parquet"
        if not src.exists():
            raise FileNotFoundError(f"bronze missing: {src}; run ingest first")
        audit = Audit()
        sink = ParquetSink(cfg.silver_dir / name / f"{cohort_id}.parquet", silver_schema(contract))
        columns = contract.field_names + ["_cohort_id"]
        for row in read_rows(src, columns=columns):
            sink.add(deid.deidentify(contract, row, audit))
        sink.close()
        audits[name] = audit
    built_at = datetime.now(UTC)
    stats = {
        "cohort_id": cohort_id,
        "deid_version": DEID_VERSION,
        "reference_date": deid.reference_date.isoformat(),
        "built_at": built_at.isoformat(),
        "seconds": round(time.monotonic() - started, 1),
        "tables": {name: a.to_dict() for name, a in audits.items()},
    }
    meta = cfg.silver_dir / "_meta" / f"{cohort_id}.json"
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps(stats, indent=1), encoding="utf-8")
    # The same audit as a table, so dbt can build rpt_deid_audit from it.
    audit_sink = ParquetSink(cfg.silver_dir / "_audit" / f"{cohort_id}.parquet", AUDIT_SCHEMA)
    for name, a in audits.items():
        d = a.to_dict()
        audit_sink.add(
            {
                "cohort_id": cohort_id,
                "table_name": name,
                "reference_date": deid.reference_date,
                "built_at": built_at,
                "deid_version": DEID_VERSION,
                "rows": d["rows"],
                "dropped_fields": ",".join(d["dropped_fields"]),
                "pseudonymised_values": d["pseudonymised_values"],
                "shifted_dates": d["shifted_dates"],
                "zip3_truncated": d["zip3_truncated"],
                "zip3_restricted_to_000": d["zip3_restricted_to_000"],
                "age_over_89_banded": d["age_over_89_banded"],
                "free_text_sweeps": sum(d["free_text_sweeps"].values()),
            }
        )
    audit_sink.close()
    total = sum(a.rows for a in audits.values())
    log(f"silver {cohort_id}: {total:,} rows de-identified in {stats['seconds']}s")
    return stats

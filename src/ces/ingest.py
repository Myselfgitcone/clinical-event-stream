"""Bundles in, bronze and quarantine out.

Every resource of a flattened type is validated against its contract. Rows that
pass become bronze rows, shaped exactly like the contract plus four bookkeeping
columns. Rows that fail go to ``quarantine`` with every reason and the raw
resource, so nothing is dropped and a rule change can replay them.

Bronze is identified data (synthetic, but shaped like PHI). Nothing downstream
reads it except the de-identification step.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa

from ces import fhir
from ces.config import Settings
from ces.contracts import Contract, load_contracts, validate
from ces.parquet import ParquetSink
from ces.synthea import sha256_of

BOOKKEEPING = [
    pa.field("_cohort_id", pa.string()),
    pa.field("_bundle_sha256", pa.string()),
    pa.field("_ingested_at", pa.timestamp("us", tz="UTC")),
    pa.field("_raw", pa.string()),
]

QUARANTINE_SCHEMA = pa.schema(
    [
        pa.field("contract", pa.string()),
        pa.field("contract_version", pa.int32()),
        pa.field("resource_type", pa.string()),
        pa.field("resource_id", pa.string()),
        pa.field("patient_id", pa.string()),
        pa.field("cohort_id", pa.string()),
        pa.field("bundle_sha256", pa.string()),
        pa.field("reasons", pa.string()),
        pa.field("raw", pa.string()),
        pa.field("ingested_at", pa.timestamp("us", tz="UTC")),
    ]
)


def bronze_schema(contract: Contract) -> pa.Schema:
    return pa.schema(list(contract.arrow_schema()) + BOOKKEEPING)


def ingest_cohort(cfg: Settings, cohort_id: str, log=print, contracts: dict[str, Contract] | None = None) -> dict:
    """Flatten, validate and write one cohort. Re-running overwrites the cohort's
    bronze and quarantine files, so ingest is idempotent per cohort."""
    contracts = contracts or load_contracts()
    cohort_dir = cfg.raw_dir / cohort_id
    files = fhir.bundle_files([cohort_dir])
    if not files:
        raise FileNotFoundError(f"no bundles under {cohort_dir / 'fhir'}")
    started = time.monotonic()
    now = datetime.now(UTC)

    sinks = {
        name: ParquetSink(cfg.bronze_dir / name / f"{cohort_id}.parquet", bronze_schema(c))
        for name, c in contracts.items()
    }
    quarantine = ParquetSink(cfg.bronze_dir / "quarantine" / f"{cohort_id}.parquet", QUARANTINE_SCHEMA)
    skipped: Counter = Counter()
    rejected: Counter = Counter()
    reason_counter: Counter = Counter()
    seen_keys: dict[str, set[str]] = {name: set() for name in contracts}
    duplicates: Counter = Counter()

    for i, path in enumerate(files, start=1):
        # The file name carries the patient's name, so only its hash is recorded.
        sha = sha256_of(path)
        bundle = fhir.load_bundle(path)
        rows, bundle_skipped = fhir.flatten_bundle(bundle)
        skipped.update(bundle_skipped)
        for name, pairs in rows.items():
            contract = contracts[name]
            for resource, row in pairs:
                reasons = validate(contract, row, now)
                key = row.get(contract.key)
                if not reasons and key in seen_keys[name]:
                    reasons = [f"{contract.key}: duplicate within cohort"]
                    duplicates[name] += 1
                if reasons:
                    rejected[name] += 1
                    for r in reasons:
                        reason_counter[f"{name}: {r.split(':')[0]}"] += 1
                    quarantine.add(
                        {
                            "contract": name,
                            "contract_version": contract.version,
                            "resource_type": resource["resourceType"],
                            "resource_id": str(key) if key is not None else None,
                            "patient_id": row.get("patient_id"),
                            "cohort_id": cohort_id,
                            "bundle_sha256": sha,
                            "reasons": "; ".join(reasons),
                            "raw": json.dumps(resource, separators=(",", ":")),
                            "ingested_at": now,
                        }
                    )
                    continue
                seen_keys[name].add(key)
                raw = None if row.get("parent_observation_id") else json.dumps(resource, separators=(",", ":"))
                sinks[name].add(
                    {**row, "_cohort_id": cohort_id, "_bundle_sha256": sha, "_ingested_at": now, "_raw": raw}
                )
        if i % 200 == 0:
            log(f"  {i}/{len(files)} bundles")

    counts = {name: sink.close() for name, sink in sinks.items()}
    quarantined = quarantine.close()
    stats = {
        "cohort_id": cohort_id,
        "bundles": len(files),
        "ingested_at": now.isoformat(),
        "seconds": round(time.monotonic() - started, 1),
        "rows": counts,
        "quarantined": dict(rejected),
        "quarantined_total": quarantined,
        "quarantine_reasons": dict(reason_counter.most_common()),
        "duplicates": dict(duplicates),
        "skipped_resource_types": dict(skipped.most_common()),
        "contract_versions": {name: c.version for name, c in contracts.items()},
    }
    meta = cfg.bronze_dir / "_meta" / f"{cohort_id}.json"
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps(stats, indent=1), encoding="utf-8")
    log(
        f"bronze {cohort_id}: {sum(counts.values()):,} rows, {quarantined:,} quarantined, "
        f"{sum(skipped.values()):,} resources of other types skipped, {stats['seconds']}s"
    )
    return stats


def list_cohorts(cfg: Settings) -> list[str]:
    if not cfg.raw_dir.exists():
        return []
    return sorted(p.name for p in cfg.raw_dir.iterdir() if (p / "fhir").is_dir())


def bronze_meta_path(cfg: Settings, cohort_id: str) -> Path:
    return cfg.bronze_dir / "_meta" / f"{cohort_id}.json"

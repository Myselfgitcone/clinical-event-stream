"""Bundles to bronze, quarantine and silver on the fixture cohort, including the
proof that nothing identifying from the raw bundles reaches any silver table."""

from __future__ import annotations

import json
import re
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

from ces import fhir
from ces.ingest import ingest_cohort
from ces.silver import build_silver


def _raw_identifiers(bundles: list[dict]) -> set[str]:
    """Every value in the raw bundles that identifies the patient."""
    values: set[str] = set()
    for b in bundles:
        for r in fhir.iter_resources(b):
            values.add(r["id"])
            if r["resourceType"] != "Patient":
                continue
            for n in r.get("name", []):
                values.update(n.get("given", []))
                values.add(n.get("family", ""))
            for ident in r.get("identifier", []):
                values.add(ident.get("value", ""))
            for t in r.get("telecom", []):
                values.add(t.get("value", ""))
            for a in r.get("address", []):
                values.update(a.get("line", []))
                values.add(a.get("city", ""))
                values.add(a.get("postalCode", ""))
                for e in a.get("extension", []):
                    for sub in e.get("extension", []):
                        if "valueDecimal" in sub:
                            values.add(str(sub["valueDecimal"]))
            values.add(r.get("birthDate", ""))
            for e in r.get("extension", []):
                if e.get("url", "").endswith("mothersMaidenName"):
                    values.add(e.get("valueString", ""))
            m = re.search(r"Person seed:\s*(-?\d+)", (r.get("text") or {}).get("div", ""))
            if m:
                values.add(m.group(1))
    return {v for v in values if v and len(v) >= 4}


def test_ingest_writes_bronze_meta_and_quarantine(cfg, bundles):
    stats = ingest_cohort(cfg, "c1", log=lambda m: None)
    assert stats["bundles"] == len(bundles)
    assert stats["rows"]["patient"] == len(bundles)
    assert stats["rows"]["encounter"] > 0 and stats["rows"]["claim"] > 0
    assert (cfg.bronze_dir / "quarantine" / "c1.parquet").exists()
    assert "DiagnosticReport" in stats["skipped_resource_types"]
    meta = json.loads((cfg.bronze_dir / "_meta" / "c1.json").read_text())
    assert meta["contract_versions"]["patient"] == 1


def test_ingest_is_idempotent(cfg):
    a = ingest_cohort(cfg, "c1", log=lambda m: None)
    b = ingest_cohort(cfg, "c1", log=lambda m: None)
    assert a["rows"] == b["rows"]
    assert pq.read_metadata(cfg.bronze_dir / "encounter" / "c1.parquet").num_rows == a["rows"]["encounter"]


def test_bad_resources_are_quarantined_with_reasons_not_dropped(cfg, bundles):
    # Corrupt a copy of the cohort: an encounter that ends before it starts, a
    # condition with no code, and a duplicate patient.
    fhir_dir = cfg.raw_dir / "c1" / "fhir"
    bad = json.loads(json.dumps(bundles[0]))
    enc = next(r for r in fhir.iter_resources(bad) if r["resourceType"] == "Encounter")
    enc["period"] = {"start": "2020-01-02T00:00:00Z", "end": "2020-01-01T00:00:00Z"}
    cond = next(r for r in fhir.iter_resources(bad) if r["resourceType"] == "Condition")
    cond.pop("code")
    (fhir_dir / "zz_bad.json").write_text(json.dumps(bad), encoding="utf-8")

    stats = ingest_cohort(cfg, "c1", log=lambda m: None)
    q = duckdb.sql(
        f"select contract, reasons from '{(cfg.bronze_dir / 'quarantine' / 'c1.parquet').as_posix()}'"
    ).fetchall()
    reasons: dict[str, str] = {}
    for c, r in q:
        reasons[c] = reasons.get(c, "") + " | " + r
    assert "period_end: before period_start" in reasons["encounter"]
    assert "code_system: required" in reasons["condition"] and "code: required" in reasons["condition"]
    assert "patient_id: duplicate within cohort" in reasons["patient"]
    assert stats["quarantined_total"] >= 3
    # the raw resource travels with the row
    raw = duckdb.sql(
        f"select raw from '{(cfg.bronze_dir / 'quarantine' / 'c1.parquet').as_posix()}' where contract='condition'"
    ).fetchone()[0]
    assert json.loads(raw)["resourceType"] == "Condition"


def test_no_raw_identifier_survives_into_any_silver_table(cfg, bundles, contracts):
    ingest_cohort(cfg, "c1", log=lambda m: None)
    build_silver(cfg, "c1", log=lambda m: None)
    raw_values = _raw_identifiers(bundles)
    assert len(raw_values) > 20

    silver_text = []
    for name in contracts:
        p: Path = cfg.silver_dir / name / "c1.parquet"
        table = pq.read_table(p)
        # provider_org_id is Synthea's facility id: an organisation, not a person.
        # It stays a UUID on purpose, so it is left out of the UUID sweep below.
        if "provider_org_id" in table.schema.names:
            table = table.drop_columns(["provider_org_id"])
        silver_text.append(json.dumps(table.to_pylist(), default=str))
        # dropped columns are gone from the schema itself
        for f in contracts[name].fields:
            if f.deid == "drop":
                assert f.name not in table.schema.names, (name, f.name)
    blob = "\n".join(silver_text)
    leaked = sorted(v for v in raw_values if v in blob)
    assert leaked == [], leaked

    # and no pattern that looks like an identifier either
    assert not re.search(r"\b\d{3}-\d{2}-\d{4}\b", blob)  # SSN
    assert not re.search(r"\b555-\d{3}-\d{4}\b", blob)  # Synthea phone numbers
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", blob)  # UUIDs
    assert "@" not in blob


def test_silver_audit_table_is_written(cfg):
    ingest_cohort(cfg, "c1", log=lambda m: None)
    stats = build_silver(cfg, "c1", log=lambda m: None)
    audit = pq.read_table(cfg.silver_dir / "_audit" / "c1.parquet").to_pylist()
    assert {a["table_name"] for a in audit} == set(stats["tables"])
    patient = next(a for a in audit if a["table_name"] == "patient")
    assert "ssn" in patient["dropped_fields"] and patient["pseudonymised_values"] == patient["rows"]

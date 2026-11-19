from __future__ import annotations

from datetime import date
from pathlib import Path

from ces import azure_landing
from ces.export import merge_weekly, week_start, weekly_point
from ces.synthea import Cohort, cohort_for_week


def test_week_start_is_the_iso_monday():
    assert week_start(date(2026, 11, 18)) == date(2026, 11, 16)
    assert week_start(date(2026, 11, 16)) == date(2026, 11, 16)
    assert week_start(date(2026, 11, 22)) == date(2026, 11, 16)


def test_merge_weekly_upserts_by_week_and_sorts():
    existing = [{"week_start": "2026-11-09", "patients": 10}, {"week_start": "2026-11-16", "patients": 20}]
    merged = merge_weekly(existing, {"week_start": "2026-11-16", "patients": 25})
    assert [p["week_start"] for p in merged] == ["2026-11-09", "2026-11-16"]
    assert merged[1]["patients"] == 25
    merged = merge_weekly(merged, {"week_start": "2026-11-02", "patients": 5})
    assert merged[0]["week_start"] == "2026-11-02"
    assert merge_weekly(["garbage", {"no_week": 1}], {"week_start": "2026-11-16"}) == [{"week_start": "2026-11-16"}]


def test_weekly_point_reads_the_summary_shape():
    summary = {
        "generated_at": "2026-11-18T00:00:00+00:00",
        "volumes": {"patients": 3, "encounters": 12, "conditions": 10, "observations": 31, "quarantine": 1},
        "care_gaps": {"statin_within_year_share": 0.5, "a1c_within_90d_share": None},
        "deid": {"k_anonymity": {"min_group_size": 1, "share_in_groups_under_5": 1.0}},
        "condition_pairs": [{"condition_a": "hypertension", "condition_b": "obesity"}],
        "dbt": {"tests": 91, "tests_passed": 90},
    }
    p = weekly_point(summary, date(2026, 11, 18), ["c1"])
    assert p["week_start"] == "2026-11-16" and p["patients"] == 3 and p["top_pair"] == "hypertension + obesity"
    assert p["tests"] == 91


def test_cohort_for_week_is_stable_within_a_week():
    a = cohort_for_week(date(2026, 11, 16), 300)
    b = cohort_for_week(date(2026, 11, 22), 300)
    assert a == b and a.id == "c202647" and a.reference_date == date(2026, 11, 16)
    assert Cohort(seed=20261118, patients=2000, reference_date=date(2026, 11, 18)).id == "c20261118"


class FakeUploader:
    def __init__(self):
        self.calls: list[tuple[str, str, Path]] = []

    def upload(self, filesystem, remote_path, local_path):
        self.calls.append((filesystem, remote_path, local_path))


def test_landing_is_a_no_op_for_local_target(cfg):
    up = FakeUploader()
    assert azure_landing.land(cfg, uploader=up, log=lambda m: None) == 0
    assert up.calls == []


def test_landing_plan_covers_every_layer(cfg):
    for layer, name in (
        ("bronze", "patient/c1.parquet"),
        ("silver", "patient/c1.parquet"),
        ("gold", "dim_patient.parquet"),
    ):
        p = getattr(cfg, f"{layer}_dir") / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    (cfg.bronze_dir / "quarantine").mkdir()
    (cfg.bronze_dir / "quarantine" / "c1.parquet").write_bytes(b"x")
    site = cfg.site_dir / "data"
    azure_cfg = type(cfg)(
        data_dir=cfg.data_dir,
        cache_dir=cfg.cache_dir,
        deid_salt="s",
        target="azure",
        azure_storage_account="acct",
        site_dir=cfg.data_dir / "site",
    )
    (azure_cfg.site_dir / "data").mkdir(parents=True)
    (azure_cfg.site_dir / "data" / "summary.json").write_text("{}")
    del site
    up = FakeUploader()
    n = azure_landing.land(azure_cfg, uploader=up, log=lambda m: None)
    remote = {(fs, path) for fs, path, _ in up.calls}
    assert n == 5
    assert ("bronze", "quarantine/c1.parquet") in remote
    assert ("silver", "patient/c1.parquet") in remote
    assert ("gold", "dim_patient.parquet") in remote
    assert ("published", "summary.json") in remote


def test_landing_can_be_limited_to_public_layers(cfg):
    azure_cfg = type(cfg)(
        data_dir=cfg.data_dir,
        cache_dir=cfg.cache_dir,
        deid_salt="s",
        target="azure",
        azure_storage_account="acct",
        site_dir=cfg.data_dir / "site",
    )
    (azure_cfg.gold_dir).mkdir(parents=True)
    (azure_cfg.gold_dir / "dim_date.parquet").write_bytes(b"x")
    (azure_cfg.bronze_dir / "patient").mkdir(parents=True)
    (azure_cfg.bronze_dir / "patient" / "c1.parquet").write_bytes(b"x")
    up = FakeUploader()
    azure_landing.land(azure_cfg, uploader=up, log=lambda m: None, only=["gold", "published"])
    assert {fs for fs, _, _ in up.calls} == {"gold"}

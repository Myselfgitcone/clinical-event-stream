from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ces.config import Settings
from ces.contracts import load_contracts

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def contracts():
    return load_contracts()


@pytest.fixture(scope="session")
def bundles() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(FIXTURES.glob("bundle_*.json"))]


@pytest.fixture
def cfg(tmp_path: Path) -> Settings:
    """A Settings pointing at a temp data dir with the fixture bundles as cohort c1."""
    data = tmp_path / "data"
    fhir = data / "raw" / "c1" / "fhir"
    fhir.mkdir(parents=True)
    for p in sorted(FIXTURES.glob("bundle_*.json")):
        shutil.copy(p, fhir / p.name)
    (data / "raw" / "c1" / "cohort.json").write_text(
        json.dumps({"cohort_id": "c1", "seed": 1, "reference_date": "2026-11-18"}), encoding="utf-8"
    )
    return Settings(data_dir=data, cache_dir=tmp_path / "cache", deid_salt="test-salt", target="local")

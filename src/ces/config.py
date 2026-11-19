"""Runtime settings. Everything comes from the environment with a local default,
so the same code runs on a laptop, in GitHub Actions and against Azure."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SYNTHEA_VERSION = "v4.0.0"
SYNTHEA_JAR_URL = (
    f"https://github.com/synthetichealth/synthea/releases/download/{SYNTHEA_VERSION}/synthea-with-dependencies.jar"
)
SYNTHEA_JAR_SHA256 = "ed43c20ad40ba5c3bc724503a5af032715fe3c491620b766148e7c2361e6ecc1"

# The eight FHIR resource types this project flattens. Everything else in a
# bundle (DiagnosticReport, DocumentReference, ExplanationOfBenefit, CarePlan,
# Provenance, ...) is counted and skipped on purpose; see README "Limits".
RESOURCE_TYPES: dict[str, str] = {
    "Patient": "patient",
    "Encounter": "encounter",
    "Condition": "condition",
    "Observation": "observation",
    "MedicationRequest": "medication_request",
    "Procedure": "procedure",
    "Immunization": "immunization",
    "Claim": "claim",
}

# ZIP3 prefixes with fewer than 20,000 residents per the 2010 Census; Safe
# Harbor says these become 000. The list is the one HHS publishes in its
# de-identification guidance (45 CFR 164.514(b)(2)(i)(B)).
RESTRICTED_ZIP3 = frozenset("036 059 063 102 203 556 692 790 821 823 830 831 878 879 884 890 893".split())


def _env(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    target: str = field(default_factory=lambda: _env("CES_TARGET", "local"))
    data_dir: Path = field(default_factory=lambda: Path(_env("CES_DATA_DIR", str(REPO_ROOT / "data"))))
    cache_dir: Path = field(default_factory=lambda: Path(_env("CES_CACHE_DIR", str(REPO_ROOT / ".cache"))))
    site_dir: Path = field(default_factory=lambda: REPO_ROOT / "site")
    transform_dir: Path = field(default_factory=lambda: REPO_ROOT / "transform")
    # Secret that keys the HMAC pseudonyms and the per-patient date shift.
    # The default exists so the pipeline runs with no setup; CI and Azure runs set their own.
    deid_salt: str = field(default_factory=lambda: _env("CES_DEID_SALT", "local-dev-salt-change-me"))
    # Where the published feeds live, so a weekly run can extend the series it finds there.
    published_base_url: str = field(
        default_factory=lambda: _env("CES_PUBLISHED_BASE_URL", "https://myselfgitcone.github.io/clinical-event-stream")
    )
    # Azure (only read when target == "azure")
    azure_storage_account: str = field(default_factory=lambda: _env("CES_AZURE_STORAGE_ACCOUNT", ""))
    azure_storage_key: str = field(default_factory=lambda: _env("CES_AZURE_STORAGE_KEY", ""))
    java_opts: str = field(default_factory=lambda: _env("CES_JAVA_OPTS", "-Xmx4g"))

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def bronze_dir(self) -> Path:
        return self.data_dir / "bronze"

    @property
    def silver_dir(self) -> Path:
        return self.data_dir / "silver"

    @property
    def gold_dir(self) -> Path:
        return self.data_dir / "gold"

    @property
    def warehouse_path(self) -> Path:
        return self.data_dir / "warehouse" / "clinical.duckdb"

    @property
    def jar_path(self) -> Path:
        return self.cache_dir / "synthea-with-dependencies.jar"


def settings() -> Settings:
    return Settings()

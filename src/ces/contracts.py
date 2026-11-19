"""Data contracts: one YAML per resource type under ``contracts/``.

A contract names every field in the flattened row, its type, whether it is
required, its allowed values and range, which Safe Harbor identifier class it
belongs to, and what the de-identification step does with it. It drives

* validation at ingest (rows that fail go to quarantine with the reasons),
* the Arrow schema of the bronze and silver parquet files,
* the de-identification step (``deid`` per field),
* and a test that every PHI-class field has a de-id action other than ``keep``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import yaml

from ces.config import REPO_ROOT

CONTRACTS_DIR = REPO_ROOT / "contracts"

PHI_CLASSES = {
    "name",
    "geo",
    "date",
    "phone",
    "fax",
    "email",
    "ssn",
    "mrn",
    "health_plan_id",
    "account",
    "license",
    "vehicle",
    "device",
    "url",
    "ip",
    "biometric",
    "photo",
    "other_unique_id",
}
DEID_ACTIONS = {"keep", "drop", "pseudonym", "shift", "zip3", "birth_year_capped"}
TYPES = {"string", "integer", "number", "boolean", "date", "datetime"}


@dataclass(frozen=True)
class Field:
    name: str
    type: str
    required: bool = False
    phi: str = "none"
    deid: str = "keep"
    enum: tuple[str, ...] | None = None
    pattern: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    # free text is swept for identifier-shaped strings (URLs, IPs, SSNs, phones, emails)
    free_text: bool = False

    @property
    def is_phi(self) -> bool:
        return self.phi != "none"


@dataclass(frozen=True)
class Contract:
    name: str
    version: int
    resource_type: str
    key: str
    fields: tuple[Field, ...]
    rules: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def field(self, name: str) -> Field:
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(name)

    @property
    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]

    def silver_fields(self) -> list[Field]:
        return [f for f in self.fields if f.deid != "drop"]

    def arrow_schema(self, silver: bool = False) -> pa.Schema:
        fields = self.silver_fields() if silver else list(self.fields)
        out = []
        for f in fields:
            t = f.type
            if silver and f.deid == "birth_year_capped":
                out.append(pa.field("birth_year", pa.int32(), nullable=True))
                continue
            out.append(pa.field(f.name, _ARROW[t], nullable=True))
        return pa.schema(out)


_ARROW = {
    "string": pa.string(),
    "integer": pa.int64(),
    "number": pa.float64(),
    "boolean": pa.bool_(),
    "date": pa.date32(),
    "datetime": pa.timestamp("us", tz="UTC"),
}


def load_contract(path: Path) -> Contract:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    fields = []
    for raw in doc["fields"]:
        f = Field(
            name=raw["name"],
            type=raw["type"],
            required=bool(raw.get("required", False)),
            phi=raw.get("phi", "none"),
            deid=raw.get("deid", "keep"),
            enum=tuple(raw["enum"]) if raw.get("enum") else None,
            pattern=raw.get("pattern"),
            minimum=raw.get("minimum"),
            maximum=raw.get("maximum"),
            free_text=bool(raw.get("free_text", False)),
        )
        if f.type not in TYPES:
            raise ValueError(f"{path.name}: field {f.name} has unknown type {f.type}")
        if f.phi != "none" and f.phi not in PHI_CLASSES:
            raise ValueError(f"{path.name}: field {f.name} has unknown phi class {f.phi}")
        if f.deid not in DEID_ACTIONS:
            raise ValueError(f"{path.name}: field {f.name} has unknown deid action {f.deid}")
        fields.append(f)
    return Contract(
        name=doc["name"],
        version=int(doc["version"]),
        resource_type=doc["resource_type"],
        key=doc["key"],
        fields=tuple(fields),
        rules=tuple(doc.get("rules") or ()),
    )


def load_contracts(directory: Path = CONTRACTS_DIR) -> dict[str, Contract]:
    out = {}
    for p in sorted(directory.glob("*.yaml")):
        c = load_contract(p)
        out[c.name] = c
    return out


# ---------------------------------------------------------------- validation


_TYPE_CHECK = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "date": lambda v: isinstance(v, date) and not isinstance(v, datetime),
    "datetime": lambda v: isinstance(v, datetime),
}


def validate(contract: Contract, row: dict[str, Any], now: datetime | None = None) -> list[str]:
    """Every reason the row violates the contract; empty means it passes."""
    now = now or datetime.now(UTC)
    reasons: list[str] = []
    unknown = set(row) - set(contract.field_names)
    if unknown:
        reasons.append(f"unknown fields: {sorted(unknown)}")
    for f in contract.fields:
        v = row.get(f.name)
        if v is None:
            if f.required:
                reasons.append(f"{f.name}: required")
            continue
        if not _TYPE_CHECK[f.type](v):
            reasons.append(f"{f.name}: expected {f.type}, got {type(v).__name__}")
            continue
        # Reasons travel into the quarantine report in gold, so a PHI field's
        # value is never written into them.
        shown = "<redacted>" if f.is_phi else repr(v)
        if f.enum and v not in f.enum:
            reasons.append(f"{f.name}: {shown} not in allowed values")
        if f.pattern and not re.fullmatch(f.pattern, v):
            reasons.append(f"{f.name}: {shown} does not match {f.pattern}")
        if f.minimum is not None and v < f.minimum:
            reasons.append(f"{f.name}: {shown} below minimum {f.minimum}")
        if f.maximum is not None and v > f.maximum:
            reasons.append(f"{f.name}: {shown} above maximum {f.maximum}")
    for rule in contract.rules:
        reason = _apply_rule(rule, row, now)
        if reason:
            reasons.append(reason)
    return reasons


def _as_dt(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day, tzinfo=UTC)
    return None


def _apply_rule(rule: dict[str, Any], row: dict[str, Any], now: datetime) -> str | None:
    kind = rule["kind"]
    if kind == "not_future":
        v = _as_dt(row.get(rule["field"]))
        if v is not None and v > now:
            return f"{rule['field']}: in the future"
    elif kind == "not_before":
        a = _as_dt(row.get(rule["field"]))
        b = _as_dt(row.get(rule["than"]))
        if a is not None and b is not None and a < b:
            return f"{rule['field']}: before {rule['than']}"
    elif kind == "requires_any":
        gate = rule.get("unless_positive")
        if gate and (row.get(gate) or 0) > 0:
            return None
        if all(row.get(f) is None for f in rule["fields"]):
            return f"none of {rule['fields']} present"
    else:
        raise ValueError(f"unknown rule kind {kind}")
    return None

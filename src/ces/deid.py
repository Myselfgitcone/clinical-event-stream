"""De-identification, HIPAA Safe Harbor style, applied between bronze and silver.

The eighteen identifier classes in 45 CFR 164.514(b)(2) and what happens here:

 1. names                      dropped (patient, maiden, mother's maiden, reference display names)
 2. geography below state      street, city, lat/lon dropped; ZIP kept as ZIP3, 000 for the
                               17 low-population prefixes HHS lists
 3. dates (except year)        every date shifted by a per-patient offset of up to a year;
                               birth date reduced to the shifted year; ages over 89 banded as 90+
 4. phone numbers              dropped
 5. fax numbers                dropped
 6. email addresses            dropped
 7. SSN                        dropped
 8. medical record numbers     dropped
 9. health plan beneficiary #  dropped
10. account numbers            dropped (none in Synthea; class is declared so a future field is caught)
11. certificate/licence #      dropped (driver's licence, passport)
12. vehicle identifiers        dropped (none in Synthea; declared)
13. device identifiers         Device resources are not flattened; declared
14. URLs                       dropped (photo URL); free text swept
15. IP addresses               free text swept
16. biometric identifiers      dropped with the photo
17. full-face photographs      dropped
18. any other unique number    every resource id replaced by an HMAC pseudonym; Synthea's
                               narrative with its person seed dropped

Date shifting keeps intervals inside a patient's record intact, which the care-gap
measures need. Strict Safe Harbor would keep only the year; the README says so.

The pseudonym and the shift are both HMAC-SHA256 of the raw id under a secret
salt. The mapping is never written anywhere.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import pyarrow as pa

from ces.config import RESTRICTED_ZIP3
from ces.contracts import Contract

MAX_SHIFT_DAYS = 365
AGE_CAP = 89
AGE_BANDS = [
    (0, 17, "0-17"),
    (18, 34, "18-34"),
    (35, 49, "35-49"),
    (50, 64, "50-64"),
    (65, 79, "65-79"),
    (80, 89, "80-89"),
]

# Patterns swept out of free-text columns that survive de-identification.
SWEEP_PATTERNS = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"\b(?:\+?1[-. ]?)?(?:\(\d{3}\)|\d{3})[-. ]\d{3}[-. ]\d{4}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "ip": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "url": re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE),
}

# Extra columns silver carries beyond the contract: derived in the patient table.
SILVER_EXTRA: dict[str, list[pa.Field]] = {
    "patient": [pa.field("age_band", pa.string()), pa.field("age_over_89", pa.bool_())],
}


def silver_schema(contract: Contract) -> pa.Schema:
    base = list(contract.arrow_schema(silver=True))
    base += SILVER_EXTRA.get(contract.name, [])
    base += [pa.field("_cohort_id", pa.string()), pa.field("_deid_version", pa.int32())]
    return pa.schema(base)


DEID_VERSION = 1


def age_band(age: int) -> str:
    if age > AGE_CAP:
        return "90+"
    for lo, hi, label in AGE_BANDS:
        if lo <= age <= hi:
            return label
    return "unknown"


def zip3(postal_code: str | None) -> str | None:
    if not postal_code:
        return None
    digits = re.sub(r"\D", "", postal_code)
    if len(digits) < 5:
        return None
    prefix = digits[:3]
    return "000" if prefix in RESTRICTED_ZIP3 else prefix


def years_between(born: date, on: date) -> int:
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


@dataclass
class Audit:
    rows: int = 0
    dropped_fields: set[str] = field(default_factory=set)
    pseudonymised: int = 0
    shifted: int = 0
    zip3: int = 0
    zip3_restricted: int = 0
    age_over_89: int = 0
    swept: Counter = field(default_factory=Counter)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "dropped_fields": sorted(self.dropped_fields),
            "pseudonymised_values": self.pseudonymised,
            "shifted_dates": self.shifted,
            "zip3_truncated": self.zip3,
            "zip3_restricted_to_000": self.zip3_restricted,
            "age_over_89_banded": self.age_over_89,
            "free_text_sweeps": dict(self.swept),
        }


class Deidentifier:
    """Applies a contract's ``deid`` actions to rows. One instance per run; the
    salt decides the pseudonyms and the shifts."""

    def __init__(self, salt: str, reference_date: date):
        if not salt:
            raise ValueError("de-identification needs a non-empty salt")
        self._key = salt.encode("utf-8")
        self.reference_date = reference_date

    # -- primitives -------------------------------------------------------
    def pseudonym(self, value: str) -> str:
        return hmac.new(self._key, b"id:" + value.encode("utf-8"), hashlib.sha256).hexdigest()[:32]

    def shift_days(self, patient_id: str) -> int:
        """Deterministic per patient, uniform in [-365, 365] without 0."""
        digest = hmac.new(self._key, b"shift:" + patient_id.encode("utf-8"), hashlib.sha256).digest()
        n = int.from_bytes(digest[:8], "big") % (2 * MAX_SHIFT_DAYS)
        return n - MAX_SHIFT_DAYS if n < MAX_SHIFT_DAYS else n - MAX_SHIFT_DAYS + 1

    def shift(self, value: datetime | date | None, patient_id: str) -> datetime | date | None:
        if value is None:
            return None
        return value + timedelta(days=self.shift_days(patient_id))

    @staticmethod
    def sweep(text: str | None, audit: Audit | None = None) -> str | None:
        if not text:
            return text
        for name, pat in SWEEP_PATTERNS.items():
            text, n = pat.subn("[removed]", text)
            if n and audit is not None:
                audit.swept[name] += n
        return text

    # -- rows -------------------------------------------------------------
    def deidentify(self, contract: Contract, row: dict[str, Any], audit: Audit | None = None) -> dict[str, Any]:
        audit = audit if audit is not None else Audit()
        audit.rows += 1
        patient_id = row.get("patient_id")
        if not patient_id:
            raise ValueError(f"{contract.name} row without patient_id cannot be de-identified")
        out: dict[str, Any] = {}
        for f in contract.fields:
            v = row.get(f.name)
            action = f.deid
            if action == "drop":
                audit.dropped_fields.add(f.name)
                continue
            if v is None:
                out["birth_year" if action == "birth_year_capped" else f.name] = None
                continue
            if action == "keep":
                out[f.name] = self.sweep(v, audit) if (f.free_text and isinstance(v, str)) else v
            elif action == "pseudonym":
                out[f.name] = self.pseudonym(str(v))
                audit.pseudonymised += 1
            elif action == "shift":
                out[f.name] = self.shift(v, patient_id)
                audit.shifted += 1
            elif action == "zip3":
                z = zip3(v)
                out[f.name] = z
                audit.zip3 += 1
                if z == "000":
                    audit.zip3_restricted += 1
            elif action == "birth_year_capped":
                born: date = v
                age = years_between(born, self.reference_date)
                shifted = self.shift(born, patient_id)
                over = age > AGE_CAP
                out["birth_year"] = None if over else shifted.year
                out["age_band"] = age_band(age)
                out["age_over_89"] = over
                audit.shifted += 1
                if over:
                    audit.age_over_89 += 1
            else:  # pragma: no cover - contracts are validated on load
                raise ValueError(action)
        if contract.name == "patient" and "age_band" not in out:
            out["age_band"] = None
            out["age_over_89"] = None
        out["_cohort_id"] = row.get("_cohort_id")
        out["_deid_version"] = DEID_VERSION
        return out

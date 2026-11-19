"""Flatten FHIR R4 resources into the contract-shaped rows the pipeline works with.

Only the eight resource types in ``RESOURCE_TYPES`` are flattened. The functions
here know nothing about de-identification: they pull every field the contracts
name, identifiers included, so that bronze is a faithful copy of the source and
the de-id step has something to prove itself against.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ces.config import RESOURCE_TYPES

Row = dict[str, Any]

NPI_SYSTEM = "http://hl7.org/fhir/sid/us-npi"
SSN_SYSTEM = "http://hl7.org/fhir/sid/us-ssn"
EXT = {
    "race": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-race",
    "ethnicity": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity",
    "birthsex": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-birthsex",
    "mothers_maiden_name": "http://hl7.org/fhir/StructureDefinition/patient-mothersMaidenName",
    "birthplace": "http://hl7.org/fhir/StructureDefinition/patient-birthPlace",
    "geolocation": "http://hl7.org/fhir/StructureDefinition/geolocation",
}


# ---------------------------------------------------------------- primitives


def parse_datetime(value: str | None) -> datetime | None:
    """FHIR dateTime/instant to an aware UTC datetime. Partial dates (YYYY, YYYY-MM)
    become the first instant of that period."""
    if not value:
        return None
    s = value.strip()
    if len(s) == 4:
        s += "-01-01"
    elif len(s) == 7:
        s += "-01"
    if len(s) == 10:
        return datetime.fromisoformat(s).replace(tzinfo=UTC)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    s = value.strip()
    if len(s) == 4:
        s += "-01-01"
    elif len(s) == 7:
        s += "-01"
    return date.fromisoformat(s[:10])


def ref_id(ref: dict | None) -> str | None:
    """``urn:uuid:<id>`` or ``Type/<id>`` to ``<id>``; conditional references
    (``Type?identifier=system|value``) to ``value``."""
    if not ref or not ref.get("reference"):
        return None
    r: str = ref["reference"]
    if r.startswith("urn:uuid:"):
        return r[9:]
    if "?identifier=" in r:
        return r.rsplit("|", 1)[-1]
    return r.rsplit("/", 1)[-1]


def coding(cc: dict | None, i: int = 0) -> dict:
    if not cc:
        return {}
    cods = cc.get("coding") or []
    return cods[i] if len(cods) > i else {}


def first(xs: list | None) -> dict:
    return (xs or [{}])[0] or {}


def ext(resource: dict, url: str) -> dict | None:
    for e in resource.get("extension") or []:
        if e.get("url") == url:
            return e
    return None


def ext_text(resource: dict, url: str) -> str | None:
    e = ext(resource, url)
    if not e:
        return None
    for sub in e.get("extension") or []:
        if sub.get("url") == "text":
            return sub.get("valueString")
    return e.get("valueString") or e.get("valueCode")


def identifier_by_type(resource: dict, type_code: str) -> str | None:
    for ident in resource.get("identifier") or []:
        if coding(ident.get("type")).get("code") == type_code:
            return ident.get("value")
    return None


def identifier_by_system(resource: dict, system: str) -> str | None:
    for ident in resource.get("identifier") or []:
        if ident.get("system") == system:
            return ident.get("value")
    return None


# ---------------------------------------------------------------- per resource


def flatten_patient(r: dict) -> Row:
    official = next((n for n in r.get("name") or [] if n.get("use") == "official"), first(r.get("name")))
    maiden = next((n for n in r.get("name") or [] if n.get("use") == "maiden"), None)
    telecom = {t.get("system"): t.get("value") for t in r.get("telecom") or []}
    addr = first(r.get("address"))
    geo = ext(addr, EXT["geolocation"]) if addr else None
    lat = lon = None
    if geo:
        for sub in geo.get("extension") or []:
            if sub.get("url") == "latitude":
                lat = sub.get("valueDecimal")
            elif sub.get("url") == "longitude":
                lon = sub.get("valueDecimal")
    birthplace = (ext(r, EXT["birthplace"]) or {}).get("valueAddress") or {}
    photo = first(r.get("photo"))
    multiple = r.get("multipleBirthBoolean")
    if multiple is None and r.get("multipleBirthInteger") is not None:
        multiple = True
    return {
        "patient_id": r.get("id"),
        "mrn": identifier_by_type(r, "MR"),
        "ssn": identifier_by_type(r, "SS") or identifier_by_system(r, SSN_SYSTEM),
        "drivers_license": identifier_by_type(r, "DL"),
        "passport": identifier_by_type(r, "PPN"),
        "family_name": official.get("family"),
        "given_name": " ".join(official.get("given") or []) or None,
        "name_prefix": " ".join(official.get("prefix") or []) or None,
        "maiden_name": maiden.get("family") if maiden else None,
        "mothers_maiden_name": ext_text(r, EXT["mothers_maiden_name"]),
        "phone": telecom.get("phone"),
        "fax": telecom.get("fax"),
        "email": telecom.get("email"),
        "photo_url": photo.get("url") or ("data:inline" if photo.get("data") else None),
        "gender": r.get("gender"),
        "birth_date": parse_date(r.get("birthDate")),
        "deceased_datetime": parse_datetime(r.get("deceasedDateTime")),
        "marital_status": coding(r.get("maritalStatus")).get("code") or (r.get("maritalStatus") or {}).get("text"),
        "race": ext_text(r, EXT["race"]),
        "ethnicity": ext_text(r, EXT["ethnicity"]),
        "birth_sex": ext_text(r, EXT["birthsex"]),
        "multiple_birth": multiple,
        "language": coding(first(r.get("communication")).get("language")).get("code"),
        "address_line": " ".join(addr.get("line") or []) or None,
        "city": addr.get("city"),
        "state": addr.get("state"),
        "postal_code": addr.get("postalCode"),
        "country": addr.get("country"),
        "latitude": lat,
        "longitude": lon,
        "birthplace_city": birthplace.get("city"),
        "birthplace_state": birthplace.get("state"),
        "narrative": (r.get("text") or {}).get("div"),
    }


def flatten_encounter(r: dict) -> Row:
    period = r.get("period") or {}
    typ = coding(first(r.get("type")))
    reason = coding(first(r.get("reasonCode")))
    participant = first(r.get("participant"))
    individual = participant.get("individual") or {}
    provider = r.get("serviceProvider") or {}
    return {
        "encounter_id": r.get("id"),
        "patient_id": ref_id(r.get("subject")),
        "patient_display": (r.get("subject") or {}).get("display"),
        "status": r.get("status"),
        "class_code": (r.get("class") or {}).get("code"),
        "type_code": typ.get("code"),
        "type_display": typ.get("display"),
        "period_start": parse_datetime(period.get("start")),
        "period_end": parse_datetime(period.get("end")),
        "reason_code": reason.get("code"),
        "reason_display": reason.get("display"),
        "provider_org_id": ref_id(provider),
        "provider_org_name": provider.get("display"),
        "practitioner_npi": ref_id(individual) if NPI_SYSTEM in (individual.get("reference") or "") else None,
        "practitioner_name": individual.get("display"),
        "location_name": (first(r.get("location")).get("location") or {}).get("display"),
    }


def flatten_condition(r: dict) -> Row:
    code = coding(r.get("code"))
    return {
        "condition_id": r.get("id"),
        "patient_id": ref_id(r.get("subject")),
        "encounter_id": ref_id(r.get("encounter")),
        "clinical_status": coding(r.get("clinicalStatus")).get("code"),
        "verification_status": coding(r.get("verificationStatus")).get("code"),
        "category": coding(first(r.get("category"))).get("code"),
        "code_system": code.get("system"),
        "code": code.get("code"),
        "display": code.get("display") or (r.get("code") or {}).get("text"),
        "onset_datetime": parse_datetime(r.get("onsetDateTime")),
        "abatement_datetime": parse_datetime(r.get("abatementDateTime")),
        "recorded_date": parse_datetime(r.get("recordedDate")),
    }


def _observation_value(o: dict) -> dict:
    q = o.get("valueQuantity") or {}
    vcc = coding(o.get("valueCodeableConcept"))
    return {
        "value_quantity": q.get("value"),
        "value_unit": q.get("unit") or q.get("code"),
        "value_string": o.get("valueString"),
        "value_code": vcc.get("code"),
        "value_display": vcc.get("display"),
    }


def flatten_observation(r: dict) -> list[Row]:
    """A parent row, plus one row per component. Blood pressure is the common case:
    one Observation with systolic and diastolic as components and no value of its own."""
    code = coding(r.get("code"))
    components = r.get("component") or []
    base = {
        "patient_id": ref_id(r.get("subject")),
        "encounter_id": ref_id(r.get("encounter")),
        "status": r.get("status"),
        "category": coding(first(r.get("category"))).get("code"),
        "effective_datetime": parse_datetime(
            r.get("effectiveDateTime") or (r.get("effectivePeriod") or {}).get("start")
        ),
        "issued": parse_datetime(r.get("issued")),
    }
    parent = {
        "observation_id": r.get("id"),
        "parent_observation_id": None,
        **base,
        "code_system": code.get("system"),
        "code": code.get("code"),
        "display": code.get("display") or (r.get("code") or {}).get("text"),
        **_observation_value(r),
        "component_count": len(components),
    }
    rows = [parent]
    for i, comp in enumerate(components, start=1):
        ccode = coding(comp.get("code"))
        rows.append(
            {
                "observation_id": f"{r.get('id')}#{i}",
                "parent_observation_id": r.get("id"),
                **base,
                "code_system": ccode.get("system"),
                "code": ccode.get("code"),
                "display": ccode.get("display"),
                **_observation_value(comp),
                "component_count": 0,
            }
        )
    return rows


def flatten_medication_request(r: dict, medications: dict[str, dict] | None = None) -> Row:
    """``medication[x]`` is a choice type: usually an inline CodeableConcept, but
    for compounded or administered drugs Synthea emits a reference to a Medication
    resource in the same bundle. Both are resolved to one code."""
    med_cc = r.get("medicationCodeableConcept")
    if not med_cc and r.get("medicationReference") and medications is not None:
        target = medications.get(ref_id(r["medicationReference"]) or "")
        med_cc = (target or {}).get("code")
    med = coding(med_cc)
    requester = r.get("requester") or {}
    return {
        "medication_request_id": r.get("id"),
        "patient_id": ref_id(r.get("subject")),
        "encounter_id": ref_id(r.get("encounter")),
        "status": r.get("status"),
        "intent": r.get("intent"),
        "category": coding(first(r.get("category"))).get("code"),
        "code_system": med.get("system"),
        "code": med.get("code"),
        "display": med.get("display") or (med_cc or {}).get("text"),
        "authored_on": parse_datetime(r.get("authoredOn")),
        "requester_npi": ref_id(requester) if NPI_SYSTEM in (requester.get("reference") or "") else None,
        "requester_name": requester.get("display"),
        "reason_condition_id": ref_id(first(r.get("reasonReference"))),
    }


def flatten_procedure(r: dict) -> Row:
    code = coding(r.get("code"))
    period = r.get("performedPeriod") or {}
    start = period.get("start") or r.get("performedDateTime")
    return {
        "procedure_id": r.get("id"),
        "patient_id": ref_id(r.get("subject")),
        "encounter_id": ref_id(r.get("encounter")),
        "status": r.get("status"),
        "code_system": code.get("system"),
        "code": code.get("code"),
        "display": code.get("display") or (r.get("code") or {}).get("text"),
        "performed_start": parse_datetime(start),
        "performed_end": parse_datetime(period.get("end")),
        "reason_condition_id": ref_id(first(r.get("reasonReference"))),
        "location_name": (r.get("location") or {}).get("display"),
    }


def flatten_immunization(r: dict) -> Row:
    code = coding(r.get("vaccineCode"))
    return {
        "immunization_id": r.get("id"),
        "patient_id": ref_id(r.get("patient")),
        "encounter_id": ref_id(r.get("encounter")),
        "status": r.get("status"),
        "code_system": code.get("system"),
        "code": code.get("code"),
        "display": code.get("display") or (r.get("vaccineCode") or {}).get("text"),
        "occurrence_datetime": parse_datetime(r.get("occurrenceDateTime")),
        "location_name": (r.get("location") or {}).get("display"),
    }


def flatten_claim(r: dict) -> Row:
    period = r.get("billablePeriod") or {}
    insurance = first(r.get("insurance"))
    coverage = insurance.get("coverage") or {}
    provider = r.get("provider") or {}
    total = r.get("total") or {}
    encounter_id = None
    for item in r.get("item") or []:
        enc = first(item.get("encounter"))
        if enc:
            encounter_id = ref_id(enc)
            break
    return {
        "claim_id": r.get("id"),
        "patient_id": ref_id(r.get("patient")),
        "patient_display": (r.get("patient") or {}).get("display"),
        "encounter_id": encounter_id,
        "status": r.get("status"),
        "claim_type": coding(r.get("type")).get("code"),
        "use": r.get("use"),
        "billable_start": parse_datetime(period.get("start")),
        "billable_end": parse_datetime(period.get("end")),
        "created": parse_datetime(r.get("created")),
        "provider_org_id": ref_id(provider),
        "provider_org_name": provider.get("display"),
        "payer_name": coverage.get("display") or ref_id(coverage),
        "member_id": (coverage.get("identifier") or {}).get("value") or insurance.get("identifier", {}).get("value"),
        "total_value": total.get("value"),
        "total_currency": total.get("currency"),
        "diagnosis_count": len(r.get("diagnosis") or []),
        "item_count": len(r.get("item") or []),
    }


FLATTENERS = {
    "Patient": flatten_patient,
    "Encounter": flatten_encounter,
    "Condition": flatten_condition,
    "Observation": flatten_observation,
    "MedicationRequest": flatten_medication_request,
    "Procedure": flatten_procedure,
    "Immunization": flatten_immunization,
    "Claim": flatten_claim,
}


def flatten_resource(resource: dict, medications: dict[str, dict] | None = None) -> list[Row]:
    rt = resource["resourceType"]
    if rt == "MedicationRequest":
        out = flatten_medication_request(resource, medications)
    else:
        out = FLATTENERS[rt](resource)
    return out if isinstance(out, list) else [out]


# ---------------------------------------------------------------- bundles


def iter_resources(bundle: dict) -> Iterator[dict]:
    for entry in bundle.get("entry") or []:
        res = entry.get("resource")
        if res and res.get("resourceType"):
            yield res


def load_bundle(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def flatten_bundle(bundle: dict) -> tuple[dict[str, list[tuple[dict, Row]]], Counter]:
    """Returns rows per contract name, each paired with its source resource, plus
    a count of the resource types that were skipped."""
    rows: dict[str, list[tuple[dict, Row]]] = {name: [] for name in RESOURCE_TYPES.values()}
    skipped: Counter = Counter()
    medications = {res.get("id"): res for res in iter_resources(bundle) if res["resourceType"] == "Medication"}
    for res in iter_resources(bundle):
        rt = res["resourceType"]
        if rt not in RESOURCE_TYPES:
            skipped[rt] += 1
            continue
        for row in flatten_resource(res, medications):
            rows[RESOURCE_TYPES[rt]].append((res, row))
    return rows, skipped


def bundle_files(cohort_dirs: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for d in cohort_dirs:
        files.extend(sorted((d / "fhir").glob("*.json")))
    return files

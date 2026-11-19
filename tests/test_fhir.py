from datetime import UTC, datetime

from ces import fhir
from ces.contracts import validate


def test_parse_datetime_handles_offsets_and_partials():
    assert fhir.parse_datetime("2000-08-31T07:59:28-05:00") == datetime(2000, 8, 31, 12, 59, 28, tzinfo=UTC)
    assert fhir.parse_datetime("2017-04-25T08:09:40.505-05:00").microsecond == 505000
    assert fhir.parse_datetime("2019") == datetime(2019, 1, 1, tzinfo=UTC)
    assert fhir.parse_datetime("2019-03") == datetime(2019, 3, 1, tzinfo=UTC)
    assert fhir.parse_datetime("2019-03-04") == datetime(2019, 3, 4, tzinfo=UTC)
    assert fhir.parse_datetime("2019-03-04T10:00:00Z") == datetime(2019, 3, 4, 10, tzinfo=UTC)
    assert fhir.parse_datetime(None) is None


def test_ref_id_resolves_the_three_reference_styles():
    assert fhir.ref_id({"reference": "urn:uuid:abc"}) == "abc"
    assert fhir.ref_id({"reference": "Patient/abc"}) == "abc"
    assert fhir.ref_id({"reference": "Practitioner?identifier=http://hl7.org/fhir/sid/us-npi|9999"}) == "9999"
    assert fhir.ref_id(None) is None


def test_fixture_bundles_flatten_into_every_contract(bundles, contracts):
    seen = set()
    for b in bundles:
        rows, skipped = fhir.flatten_bundle(b)
        for name, pairs in rows.items():
            for _, row in pairs:
                assert validate(contracts[name], row) == [], (name, row)
                seen.add(name)
        assert "DiagnosticReport" in skipped  # counted, not flattened
    assert {"patient", "encounter", "condition", "claim", "observation"} <= seen


def test_patient_flattening_pulls_every_identifier(bundles):
    patient = next(r for r in fhir.iter_resources(bundles[0]) if r["resourceType"] == "Patient")
    row = fhir.flatten_patient(patient)
    for field in (
        "ssn",
        "drivers_license",
        "passport",
        "mrn",
        "family_name",
        "given_name",
        "phone",
        "address_line",
        "city",
        "postal_code",
        "latitude",
        "longitude",
        "mothers_maiden_name",
        "birth_date",
        "narrative",
    ):
        assert row[field] is not None, field
    assert "Person seed" in row["narrative"]


def test_component_observations_become_child_rows():
    bp = {
        "resourceType": "Observation",
        "id": "obs1",
        "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "85354-9", "display": "Blood pressure panel"}]},
        "subject": {"reference": "urn:uuid:p1"},
        "effectiveDateTime": "2020-01-01T00:00:00Z",
        "component": [
            {
                "code": {"coding": [{"system": "http://loinc.org", "code": "8462-4", "display": "Diastolic"}]},
                "valueQuantity": {"value": 80, "unit": "mm[Hg]"},
            },
            {
                "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6", "display": "Systolic"}]},
                "valueQuantity": {"value": 120, "unit": "mm[Hg]"},
            },
        ],
    }
    rows = fhir.flatten_observation(bp)
    assert len(rows) == 3
    assert rows[0]["component_count"] == 2 and rows[0]["value_quantity"] is None
    assert rows[1]["observation_id"] == "obs1#1" and rows[1]["parent_observation_id"] == "obs1"
    assert rows[2]["code"] == "8480-6" and rows[2]["value_quantity"] == 120


def test_medication_reference_is_resolved_within_the_bundle():
    bundle = {
        "entry": [
            {
                "resource": {
                    "resourceType": "Medication",
                    "id": "m1",
                    "code": {"coding": [{"system": "rxnorm", "code": "999", "display": "Compound X"}]},
                }
            },
            {
                "resource": {
                    "resourceType": "MedicationRequest",
                    "id": "mr1",
                    "status": "active",
                    "intent": "order",
                    "subject": {"reference": "urn:uuid:p1"},
                    "authoredOn": "2020-01-01T00:00:00Z",
                    "medicationReference": {"reference": "urn:uuid:m1"},
                }
            },
        ]
    }
    rows, skipped = fhir.flatten_bundle(bundle)
    ((_, row),) = rows["medication_request"]
    assert row["code"] == "999" and row["display"] == "Compound X"
    assert skipped["Medication"] == 1


def test_claim_payer_and_encounter_link(bundles):
    claims = [r for b in bundles for r in fhir.iter_resources(b) if r["resourceType"] == "Claim"]
    rows = [fhir.flatten_claim(c) for c in claims]
    assert all(r["payer_name"] for r in rows)
    assert any(r["encounter_id"] for r in rows)

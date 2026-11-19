from datetime import UTC, date, datetime

import pytest

from ces.config import RESOURCE_TYPES
from ces.contracts import PHI_CLASSES, validate


def test_one_contract_per_flattened_resource_type(contracts):
    assert set(contracts) == set(RESOURCE_TYPES.values())
    for c in contracts.values():
        assert c.resource_type in RESOURCE_TYPES
        assert c.key in c.field_names


def test_every_phi_field_has_a_deid_action_other_than_keep(contracts):
    offenders = [(c.name, f.name) for c in contracts.values() for f in c.fields if f.is_phi and f.deid == "keep"]
    assert offenders == []


def test_every_non_phi_field_is_kept_or_explicitly_dropped(contracts):
    for c in contracts.values():
        for f in c.fields:
            if not f.is_phi:
                assert f.deid in ("keep", "drop"), (c.name, f.name)


def test_all_eighteen_classes_are_known():
    assert len(PHI_CLASSES) == 18


def test_every_contract_has_patient_id_and_pseudonymises_it(contracts):
    for c in contracts.values():
        assert c.field("patient_id").deid == "pseudonym", c.name


def test_valid_row_passes(contracts):
    row = {
        "condition_id": "x",
        "patient_id": "p",
        "code_system": "http://snomed.info/sct",
        "code": "44054006",
        "onset_datetime": datetime(2020, 1, 1, tzinfo=UTC),
    }
    assert validate(contracts["condition"], row) == []


def test_missing_required_and_bad_enum_are_reported(contracts):
    row = {"encounter_id": "e", "patient_id": "p", "status": "finished", "class_code": "WRONG"}
    reasons = validate(contracts["encounter"], row)
    assert any(r.startswith("period_start: required") for r in reasons)
    assert any(r.startswith("class_code:") and "not in allowed values" in r for r in reasons)


def test_rules_catch_future_and_inverted_periods(contracts):
    row = {
        "encounter_id": "e",
        "patient_id": "p",
        "status": "finished",
        "class_code": "AMB",
        "period_start": datetime(2030, 1, 1, tzinfo=UTC),
        "period_end": datetime(2029, 1, 1, tzinfo=UTC),
    }
    reasons = validate(contracts["encounter"], row, now=datetime(2026, 11, 18, tzinfo=UTC))
    assert "period_start: in the future" in reasons
    assert "period_end: before period_start" in reasons


def test_phi_values_never_appear_in_reasons(contracts):
    row = {
        "patient_id": "p",
        "gender": "male",
        "birth_date": date(1990, 1, 1),
        "ssn": "123-45-678",  # malformed on purpose
    }
    reasons = validate(contracts["patient"], row)
    assert reasons and all("123-45" not in r for r in reasons)
    assert any("<redacted>" in r for r in reasons)


def test_requires_any_is_waived_for_component_parents(contracts):
    base = {
        "observation_id": "o",
        "patient_id": "p",
        "status": "final",
        "code_system": "http://loinc.org",
        "code": "85354-9",
        "effective_datetime": datetime(2020, 1, 1, tzinfo=UTC),
    }
    assert validate(contracts["observation"], {**base, "component_count": 2}) == []
    assert validate(contracts["observation"], {**base, "component_count": 0}) == [
        "none of ['value_quantity', 'value_string', 'value_code'] present"
    ]


@pytest.mark.parametrize("silver", [False, True])
def test_arrow_schema_matches_fields(contracts, silver):
    c = contracts["patient"]
    names = c.arrow_schema(silver=silver).names
    if silver:
        assert "ssn" not in names and "birth_year" in names and "birth_date" not in names
    else:
        assert "ssn" in names and "birth_date" in names

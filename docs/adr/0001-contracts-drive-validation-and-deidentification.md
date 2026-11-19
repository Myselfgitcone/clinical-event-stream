# ADR 0001: one contract per resource type drives validation and de-identification

**Status:** accepted, 2026-11-18

## Context

Eight FHIR R4 resource types are flattened. Each field has to be validated at
ingest, typed in parquet, and either kept, dropped, pseudonymised, shifted or
truncated before it may enter silver. Writing those rules in three places
(validator, writer, de-identifier) is how one of them drifts.

## Decision

`contracts/<type>.yaml` is the only description of a flattened row. Every field
carries `type`, `required`, optional `enum`/`pattern`/`minimum`/`maximum`, a
Safe Harbor identifier class (`phi`) and a de-identification action (`deid`).

* `ces.contracts.validate` enforces the field rules and the row rules
  (`not_future`, `not_before`, `requires_any`). Failures go to quarantine with
  every reason; PHI values never appear in the reason text.
* `Contract.arrow_schema()` is the bronze schema; `arrow_schema(silver=True)`
  drops the `drop` fields and swaps `birth_date` for `birth_year`.
* `ces.deid.Deidentifier.deidentify` reads the `deid` action per field.
* `tests/test_contracts.py` fails if any field with a `phi` class has
  `deid: keep`, so adding a field without deciding what happens to it is a
  test failure, not a leak.

## Consequences

Adding a resource type is one YAML file plus one flattener function. Changing a
rule is a contract version bump; the quarantine report keeps the version so
replayed rejects can be told apart.

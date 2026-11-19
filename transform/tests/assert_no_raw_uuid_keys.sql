-- Synthea ids are UUIDs. If one reaches gold, pseudonymisation was skipped.
with keys as (
    select patient_key as k from {{ ref('fct_encounter') }}
    union all select encounter_key from {{ ref('fct_encounter') }}
    union all select patient_key from {{ ref('fct_condition') }}
    union all select encounter_key from {{ ref('fct_condition') }}
    union all select patient_key from {{ ref('fct_observation') }}
    union all select encounter_key from {{ ref('fct_observation') }}
    union all select patient_key from {{ ref('fct_medication_request') }}
    union all select reason_condition_key from {{ ref('fct_medication_request') }}
)
select k
from keys
where k is not null
  and regexp_matches(k, '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')

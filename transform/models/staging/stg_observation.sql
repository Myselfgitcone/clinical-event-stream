select
    observation_id          as observation_key,
    parent_observation_id   as parent_observation_key,
    patient_id              as patient_key,
    encounter_id            as encounter_key,
    status,
    category,
    code_system,
    code,
    display,
    effective_datetime,
    issued,
    value_quantity,
    value_unit,
    value_string,
    value_code,
    value_display,
    component_count,
    _cohort_id              as cohort_id
from {{ source('silver', 'observation') }}
qualify row_number() over (partition by observation_id order by _cohort_id desc) = 1

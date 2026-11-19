select
    procedure_id            as procedure_key,
    patient_id              as patient_key,
    encounter_id            as encounter_key,
    status,
    code_system,
    code,
    display,
    performed_start,
    performed_end,
    reason_condition_id     as reason_condition_key,
    location_name,
    _cohort_id              as cohort_id
from {{ source('silver', 'procedure') }}
qualify row_number() over (partition by procedure_id order by _cohort_id desc) = 1

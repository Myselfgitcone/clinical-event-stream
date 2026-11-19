select
    condition_id            as condition_key,
    patient_id              as patient_key,
    encounter_id            as encounter_key,
    clinical_status,
    verification_status,
    category,
    code_system,
    code,
    display,
    onset_datetime,
    abatement_datetime,
    recorded_date,
    _cohort_id              as cohort_id
from {{ source('silver', 'condition') }}
qualify row_number() over (partition by condition_id order by _cohort_id desc) = 1

select
    immunization_id         as immunization_key,
    patient_id              as patient_key,
    encounter_id            as encounter_key,
    status,
    code_system,
    code,
    display,
    occurrence_datetime,
    location_name,
    _cohort_id              as cohort_id
from {{ source('silver', 'immunization') }}
qualify row_number() over (partition by immunization_id order by _cohort_id desc) = 1

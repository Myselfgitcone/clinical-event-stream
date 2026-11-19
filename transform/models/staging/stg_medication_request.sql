select
    medication_request_id   as medication_request_key,
    patient_id              as patient_key,
    encounter_id            as encounter_key,
    status,
    intent,
    category,
    code_system,
    code,
    display,
    authored_on,
    requester_npi,
    reason_condition_id     as reason_condition_key,
    _cohort_id              as cohort_id
from {{ source('silver', 'medication_request') }}
qualify row_number() over (partition by medication_request_id order by _cohort_id desc) = 1

select
    encounter_id                                    as encounter_key,
    patient_id                                      as patient_key,
    status,
    class_code,
    type_code,
    type_display,
    period_start,
    period_end,
    date_diff('minute', period_start, period_end)   as duration_minutes,
    reason_code,
    reason_display,
    provider_org_id,
    provider_org_name,
    practitioner_npi,
    location_name,
    _cohort_id                                      as cohort_id
from {{ source('silver', 'encounter') }}
qualify row_number() over (partition by encounter_id order by _cohort_id desc) = 1

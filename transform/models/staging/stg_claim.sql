select
    claim_id                as claim_key,
    patient_id              as patient_key,
    encounter_id            as encounter_key,
    status,
    claim_type,
    use,
    billable_start,
    billable_end,
    created,
    provider_org_id,
    provider_org_name,
    payer_name,
    total_value,
    total_currency,
    diagnosis_count,
    item_count,
    _cohort_id              as cohort_id
from {{ source('silver', 'claim') }}
qualify row_number() over (partition by claim_id order by _cohort_id desc) = 1

-- Grain: one medication order.
select
    m.medication_request_key,
    dp.patient_sk,
    m.patient_key,
    m.encounter_key,
    dm.medication_sk,
    cast(strftime(m.authored_on, '%Y%m%d') as integer)  as authored_date_key,
    m.code_system,
    m.code,
    m.display,
    dm.is_statin,
    m.status,
    m.intent,
    m.category,
    m.authored_on,
    m.requester_npi,
    m.reason_condition_key,
    m.cohort_id
from {{ ref('stg_medication_request') }} m
left join {{ ref('dim_patient') }} dp on dp.patient_key = m.patient_key and dp.is_current
left join {{ ref('dim_medication') }} dm on dm.code_system = m.code_system and dm.code = m.code

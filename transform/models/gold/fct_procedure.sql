select
    p.procedure_key,
    dp.patient_sk,
    p.patient_key,
    p.encounter_key,
    cast(strftime(p.performed_start, '%Y%m%d') as integer)  as performed_date_key,
    p.status,
    p.code_system,
    p.code,
    p.display,
    p.performed_start,
    p.performed_end,
    date_diff('minute', p.performed_start, p.performed_end) as duration_minutes,
    p.reason_condition_key,
    p.location_name,
    p.cohort_id
from {{ ref('stg_procedure') }} p
left join {{ ref('dim_patient') }} dp on dp.patient_key = p.patient_key and dp.is_current

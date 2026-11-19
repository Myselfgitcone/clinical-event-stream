-- Grain: one encounter.
select
    e.encounter_key,
    dp.patient_sk,
    e.patient_key,
    cast(strftime(e.period_start, '%Y%m%d') as integer)     as start_date_key,
    pr.provider_sk,
    py.payer_sk,
    coalesce(py.payer_name, 'UNKNOWN')                      as payer_name,
    e.status,
    e.class_code,
    e.type_code,
    e.type_display,
    e.period_start,
    e.period_end,
    e.duration_minutes,
    -- age from shifted dates and the shifted birth year; null for 90+
    case when dp.birth_year is not null then year(e.period_start) - dp.birth_year end as age_at_encounter,
    dp.age_band,
    e.reason_code,
    e.reason_display,
    e.practitioner_npi,
    e.provider_org_id,
    e.cohort_id
from {{ ref('stg_encounter') }} e
left join {{ ref('dim_patient') }} dp on dp.patient_key = e.patient_key and dp.is_current
left join {{ ref('dim_provider') }} pr on pr.provider_org_id = e.provider_org_id
left join {{ ref('int_encounter_payer') }} ep on ep.encounter_key = e.encounter_key
left join {{ ref('dim_payer') }} py on py.payer_name = ep.payer_name

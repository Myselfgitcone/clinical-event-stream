-- Grain: one recorded condition (a diagnosis event, not a disease episode).
select
    c.condition_key,
    dp.patient_sk,
    c.patient_key,
    c.encounter_key,
    dc.condition_sk,
    cast(strftime(c.onset_datetime, '%Y%m%d') as integer)   as onset_date_key,
    c.code_system,
    c.code,
    c.display,
    dc.is_chronic,
    dc.chronic_group,
    c.clinical_status,
    c.verification_status,
    c.category,
    c.onset_datetime,
    c.abatement_datetime,
    date_diff('day', c.onset_datetime, c.abatement_datetime)    as duration_days,
    case when dp.birth_year is not null then year(c.onset_datetime) - dp.birth_year end as age_at_onset,
    dp.age_band,
    coalesce(fe.payer_name, 'UNKNOWN')                          as payer_name,
    c.cohort_id
from {{ ref('stg_condition') }} c
left join {{ ref('dim_patient') }} dp on dp.patient_key = c.patient_key and dp.is_current
left join {{ ref('dim_condition') }} dc on dc.code_system = c.code_system and dc.code = c.code
left join {{ ref('fct_encounter') }} fe on fe.encounter_key = c.encounter_key

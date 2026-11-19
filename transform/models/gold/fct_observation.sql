-- Grain: one observation value. Parents of component observations (blood
-- pressure panels) carry no value of their own and are kept with component_count > 0.
select
    o.observation_key,
    o.parent_observation_key,
    dp.patient_sk,
    o.patient_key,
    o.encounter_key,
    cast(strftime(o.effective_datetime, '%Y%m%d') as integer)   as effective_date_key,
    o.status,
    o.category,
    o.code_system,
    o.code,
    o.display,
    o.effective_datetime,
    o.value_quantity,
    o.value_unit,
    o.value_string,
    o.value_code,
    o.value_display,
    o.component_count,
    o.cohort_id
from {{ ref('stg_observation') }} o
left join {{ ref('dim_patient') }} dp on dp.patient_key = o.patient_key and dp.is_current

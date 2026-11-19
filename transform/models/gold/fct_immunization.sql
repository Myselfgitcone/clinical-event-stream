select
    i.immunization_key,
    dp.patient_sk,
    i.patient_key,
    i.encounter_key,
    cast(strftime(i.occurrence_datetime, '%Y%m%d') as integer)  as occurrence_date_key,
    i.status,
    i.code_system,
    i.code,
    i.display,
    i.occurrence_datetime,
    i.location_name,
    i.cohort_id
from {{ ref('stg_immunization') }} i
left join {{ ref('dim_patient') }} dp on dp.patient_key = i.patient_key and dp.is_current

-- One row per patient pseudonym. A patient appears in exactly one cohort, but
-- the rule is still spelled out: the latest cohort's row wins.
with ranked as (
    select
        *,
        row_number() over (partition by patient_id order by _cohort_id desc) as rn
    from {{ source('silver', 'patient') }}
)
select
    patient_id                      as patient_key,
    gender,
    birth_sex,
    birth_year,
    age_band,
    age_over_89,
    deceased_datetime,
    deceased_datetime is not null   as is_deceased,
    marital_status,
    race,
    ethnicity,
    multiple_birth,
    language,
    state,
    postal_code                     as zip3,
    country,
    birthplace_state,
    _cohort_id                      as cohort_id,
    _deid_version                   as deid_version
from ranked
where rn = 1

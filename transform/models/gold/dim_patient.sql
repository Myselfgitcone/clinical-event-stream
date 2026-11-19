-- Type 2 patient dimension. One row per version of a patient's attributes; a new
-- cohort that re-emits a patient with changed attributes closes the open row.
-- Synthea never re-emits a patient, so today every patient has one version.
-- The structure is here so the facts can join on patient_sk without changing
-- when a source that does update patients is plugged in.
with versions as (
    select
        p.patient_key,
        p.cohort_id,
        c.built_at,
        md5(concat_ws('|',
            coalesce(p.gender, ''), coalesce(p.birth_sex, ''), coalesce(p.birth_year::varchar, ''),
            coalesce(p.age_band, ''), coalesce(p.marital_status, ''), coalesce(p.race, ''),
            coalesce(p.ethnicity, ''), coalesce(p.state, ''), coalesce(p.zip3, ''),
            coalesce(p.is_deceased::varchar, ''), coalesce(p.language, '')
        )) as attribute_hash,
        p.*
    from {{ ref('stg_patient') }} p
    left join {{ ref('stg_cohort') }} c using (cohort_id)
),
ordered as (
    select
        *,
        lag(attribute_hash) over (partition by patient_key order by built_at) as prev_hash,
        lead(built_at)      over (partition by patient_key order by built_at) as next_built_at
    from versions
),
changes as (
    select * from ordered where prev_hash is null or prev_hash <> attribute_hash
)
select
    md5(patient_key || ':' || attribute_hash)   as patient_sk,
    patient_key,
    gender,
    birth_sex,
    birth_year,
    age_band,
    age_over_89,
    is_deceased,
    deceased_datetime,
    marital_status,
    race,
    ethnicity,
    multiple_birth,
    language,
    state,
    zip3,
    country,
    birthplace_state,
    cohort_id,
    coalesce(built_at, timestamp '1900-01-01')  as valid_from,
    next_built_at                               as valid_to,
    next_built_at is null                       as is_current,
    attribute_hash
from changes

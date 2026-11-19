-- Two care-gap measures for type 2 diabetes, by age band and payer type.
--
--   statin_within_year: of diabetics aged 40 to 75 at diagnosis (the ADA's
--     statin recommendation), how many had a statin ordered within 365 days
--     after the diagnosis. Orders before the diagnosis do not count.
--   a1c_within_90d: of all diabetics, how many had an HbA1c (LOINC 4548-4)
--     resulted within 90 days after diagnosis, the day of diagnosis included.
--
-- Dates are shifted per patient, but every date of one patient moves by the
-- same amount, so the windows are exact.
with diagnosis as (
    select
        patient_key,
        min(onset_datetime)     as diagnosed_at,
        any_value(age_band)     as age_band,
        min_by(payer_name, onset_datetime) as payer_name,
        min_by(age_at_onset, onset_datetime) as age_at_diagnosis
    from {{ ref('fct_condition') }}
    where chronic_group = 'type 2 diabetes'
    group by 1
),
statins as (
    select d.patient_key
    from diagnosis d
    join {{ ref('fct_medication_request') }} m
      on m.patient_key = d.patient_key
     and m.is_statin
     and m.authored_on >= d.diagnosed_at
     and m.authored_on <  d.diagnosed_at + interval 365 day
    group by 1
),
a1c as (
    select d.patient_key
    from diagnosis d
    join {{ ref('fct_observation') }} o
      on o.patient_key = d.patient_key
     and o.code = '4548-4'
     and o.effective_datetime >= d.diagnosed_at
     and o.effective_datetime <  d.diagnosed_at + interval 90 day
    group by 1
),
scored as (
    select
        d.patient_key,
        d.age_band,
        coalesce(py.payer_type, case when d.payer_name = 'UNKNOWN' then 'unknown' else 'private' end) as payer_type,
        d.age_at_diagnosis between 40 and 75          as statin_eligible,
        s.patient_key is not null                     as statin_within_year,
        a.patient_key is not null                     as a1c_within_90d
    from diagnosis d
    left join {{ ref('dim_payer') }} py on py.payer_name = d.payer_name
    left join statins s using (patient_key)
    left join a1c a using (patient_key)
)
select
    age_band,
    payer_type,
    count(*)                                                        as diabetics,
    count(*) filter (where statin_eligible)                         as statin_eligible,
    count(*) filter (where statin_eligible and statin_within_year)  as statin_within_year,
    count(*) filter (where a1c_within_90d)                          as a1c_within_90d
from scored
group by 1, 2
order by 1, 2

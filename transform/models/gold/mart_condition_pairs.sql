-- Which chronic conditions co-occur in the same patient, and how much more often
-- than chance. One row per unordered pair of chronic groups.
--
--   lift = P(A and B) / (P(A) * P(B)); 1.0 means independent.
--
-- Pairs seen in fewer than 10 patients are left out: with a few thousand
-- patients their lift is noise.
with patients as (
    select count(*) as n from {{ ref('dim_patient') }} where is_current
),
chronic as (
    select distinct patient_key, chronic_group
    from {{ ref('fct_condition') }}
    where is_chronic
),
singles as (
    select chronic_group, count(*) as patients from chronic group by 1
),
pairs as (
    select
        a.chronic_group as condition_a,
        b.chronic_group as condition_b,
        count(*)        as patients_with_both
    from chronic a
    join chronic b on a.patient_key = b.patient_key and a.chronic_group < b.chronic_group
    group by 1, 2
)
select
    p.condition_a,
    p.condition_b,
    p.patients_with_both,
    sa.patients                                                     as patients_with_a,
    sb.patients                                                     as patients_with_b,
    n.n                                                             as patients_total,
    round(p.patients_with_both / n.n, 4)                            as share_of_patients,
    round(p.patients_with_both * n.n / (sa.patients * sb.patients), 2) as lift,
    round(p.patients_with_both / sa.patients, 4)                    as share_of_a_with_b,
    round(p.patients_with_both / sb.patients, 4)                    as share_of_b_with_a
from pairs p
join singles sa on sa.chronic_group = p.condition_a
join singles sb on sb.chronic_group = p.condition_b
cross join patients n
where p.patients_with_both >= 10
order by p.patients_with_both desc

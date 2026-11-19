-- How re-identifiable the de-identified patients still are on the quasi-identifiers
-- that survive Safe Harbor: age band, gender, race, ethnicity, state and ZIP3.
-- k is the size of the smallest group that shares all six. Safe Harbor does not
-- require any k; this report says what it leaves behind.
with groups as (
    select
        age_band, gender, race, ethnicity, state, zip3,
        count(*) as k
    from {{ ref('dim_patient') }}
    where is_current
    group by all
)
select
    sum(k)                                                      as patients,
    count(*)                                                    as groups,
    min(k)                                                      as min_group_size,
    round(sum(k) filter (where k < 5)  / sum(k), 4)             as share_in_groups_under_5,
    round(sum(k) filter (where k < 11) / sum(k), 4)             as share_in_groups_under_11,
    sum(k) filter (where k = 1)                                 as unique_patients,
    'age_band, gender, race, ethnicity, state, zip3'            as quasi_identifiers
from groups

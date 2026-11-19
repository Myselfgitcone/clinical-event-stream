-- What de-identification did, per silver table, summed over cohorts.
select
    table_name,
    max(deid_version)               as deid_version,
    count(distinct cohort_id)       as cohorts,
    sum(rows)                       as rows,
    any_value(dropped_fields)       as dropped_fields,
    sum(pseudonymised_values)       as pseudonymised_values,
    sum(shifted_dates)              as shifted_dates,
    sum(zip3_truncated)             as zip3_truncated,
    sum(zip3_restricted_to_000)     as zip3_restricted_to_000,
    sum(age_over_89_banded)         as age_over_89_banded,
    sum(free_text_sweeps)           as free_text_sweeps,
    max(built_at)                   as last_built_at
from {{ source('silver', '_audit') }}
group by 1
order by 1

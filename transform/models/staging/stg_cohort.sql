-- One row per cohort build, from the de-identification audit.
select
    cohort_id,
    min(reference_date)     as reference_date,
    max(built_at)           as built_at,
    max(deid_version)       as deid_version
from {{ source('silver', '_audit') }}
group by 1

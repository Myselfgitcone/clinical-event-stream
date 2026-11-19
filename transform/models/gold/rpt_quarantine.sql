-- Quarantined resources by contract and reason. A resource with two reasons
-- counts once per reason. Only the field name of each reason is kept.
with exploded as (
    select
        contract,
        contract_version,
        resource_type,
        cohort_id,
        trim(split_part(unnest(string_split(reasons, '; ')), ':', 1)) as reason,
        ingested_at
    from {{ source('bronze', 'quarantine') }}
)
select
    contract,
    contract_version,
    resource_type,
    cohort_id,
    reason,
    count(*)            as rows,
    max(ingested_at)    as last_seen
from exploded
group by 1, 2, 3, 4, 5
order by rows desc

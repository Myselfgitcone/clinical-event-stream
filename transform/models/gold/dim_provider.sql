-- Organizations that provided encounters or billed claims. Synthea's provider
-- ids are stable across cohorts because they come from a fixed facility file.
with orgs as (
    select provider_org_id, provider_org_name from {{ ref('stg_encounter') }} where provider_org_id is not null
    union all
    select provider_org_id, provider_org_name from {{ ref('stg_claim') }} where provider_org_id is not null
)
select
    md5(provider_org_id)            as provider_sk,
    provider_org_id,
    any_value(provider_org_name)    as provider_org_name,
    count(*)                        as references
from orgs
group by provider_org_id

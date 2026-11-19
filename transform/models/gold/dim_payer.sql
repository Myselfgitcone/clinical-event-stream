with payers as (
    select payer_name, count(*) as claims from {{ ref('stg_claim') }} group by 1
)
select
    md5(p.payer_name)                       as payer_sk,
    p.payer_name,
    coalesce(r.payer_type, 'private')       as payer_type,
    p.claims
from payers p
left join {{ ref('ref_payer_type') }} r using (payer_name)

{{ config(materialized='view', schema='staging') }}
-- The payer of an encounter is the payer on its (non-pharmacy) claim. An
-- encounter normally has exactly one; if several, the earliest created wins.
select
    encounter_key,
    payer_name,
    claim_key
from {{ ref('stg_claim') }}
where encounter_key is not null
  and claim_type <> 'pharmacy'
qualify row_number() over (partition by encounter_key order by created, claim_key) = 1

with codes as (
    select code_system, code, any_value(display) as display, count(*) as requests
    from {{ ref('stg_medication_request') }}
    group by 1, 2
)
select
    md5(code_system || '|' || code)                         as medication_sk,
    code_system,
    code,
    display,
    -- statins by their generic names; this is what the care-gap measure uses
    regexp_matches(lower(coalesce(display, '')),
        '(simvastatin|atorvastatin|rosuvastatin|pravastatin|lovastatin|fluvastatin|pitavastatin)') as is_statin,
    requests
from codes

with codes as (
    select code_system, code, any_value(display) as display, count(*) as occurrences
    from {{ ref('stg_condition') }}
    group by 1, 2
)
select
    md5(c.code_system || '|' || c.code)     as condition_sk,
    c.code_system,
    c.code,
    c.display,
    r.chronic_group,
    r.code is not null                      as is_chronic,
    c.occurrences
from codes c
left join {{ ref('ref_chronic_conditions') }} r on r.code = c.code

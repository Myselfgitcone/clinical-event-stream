{{ config(severity='warn') }}
-- Warn when more than half the patients sit in a quasi-identifier group smaller
-- than 5. Safe Harbor does not forbid it; the page reports it as a limit.
select *
from {{ ref('rpt_k_anonymity') }}
where share_in_groups_under_5 > 0.5

-- Numerators never exceed their denominators.
select *
from {{ ref('mart_care_gaps') }}
where statin_within_year > statin_eligible
   or statin_eligible > diabetics
   or a1c_within_90d > diabetics

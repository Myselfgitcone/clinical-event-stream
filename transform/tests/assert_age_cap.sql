-- Ages over 89 are banded as 90+ and carry no birth year; nobody else may look
-- older than 90 by their (shifted) birth year either.
select patient_key, birth_year, age_band, age_over_89
from {{ ref('dim_patient') }}
where (age_over_89 and birth_year is not null)
   or (age_over_89 and age_band <> '90+')
   or (not age_over_89 and age_band = '90+')
   or (birth_year is not null and year(current_date) - birth_year > 91)

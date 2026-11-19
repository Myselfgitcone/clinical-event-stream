-- Calendar from 1900 to 2035. Dates in the facts are shifted per patient, so
-- the calendar is a labelling device, not a claim about when anything happened.
with days as (
    select unnest(generate_series(date '1900-01-01', date '2035-12-31', interval 1 day))::date as d
)
select
    cast(strftime(d, '%Y%m%d') as integer)  as date_key,
    d                                       as date,
    year(d)                                 as year,
    quarter(d)                              as quarter,
    month(d)                                as month,
    strftime(d, '%B')                       as month_name,
    cast(strftime(d, '%V') as integer)      as iso_week,
    isodow(d)                               as iso_weekday,
    isodow(d) >= 6                          as is_weekend,
    date_trunc('week', d)::date             as week_start,
    date_trunc('month', d)::date            as month_start
from days

# ADR 0002: shift dates per patient instead of keeping only the year

**Status:** accepted, 2026-11-18

## Context

Safe Harbor's third identifier class removes "all elements of dates (except
year) for dates that are directly related to an individual". Taken literally,
every encounter, lab and prescription would carry only a year. The two measures
this project exists to answer (a statin within 365 days of a diabetes
diagnosis, an HbA1c within 90 days) need day precision between events of the
same patient.

## Decision

Every date of a patient moves by the same offset, drawn deterministically from
HMAC-SHA256(salt, patient id) in [-365, 365] days, never 0. Intervals inside a
record are exact; the absolute calendar position is wrong by up to a year and
the amount is unknowable without the salt. Birth date is reduced to the shifted
year, and anyone over 89 is banded as 90+ with no birth year at all, which is
the Safe Harbor age rule.

## Consequences

* The README and the page say plainly that this is Safe Harbor *style*: date
  shifting is the standard practice in de-identified research datasets, but a
  strict Safe Harbor release would keep only years.
* Seasonality is destroyed on purpose. Anything that asks "how many flu shots
  in October" cannot be answered from silver.
* `dim_date` is a labelling device over shifted dates. Nothing in gold should
  be read as happening on a real calendar day.
* The offset is never stored. Re-identification by date arithmetic needs the
  salt, which lives in the environment (CI secret) and nowhere in the data.

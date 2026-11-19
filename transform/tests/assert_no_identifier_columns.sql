-- No column anywhere in staging or gold may be named like a direct identifier.
-- The de-identification step drops these fields; this proves nothing re-added one.
select table_schema, table_name, column_name
from information_schema.columns
where table_schema in ('staging', 'gold')
  and regexp_matches(lower(column_name),
      '(^|_)(name|names|given|family|ssn|phone|fax|email|address|street|city|postal_code|zip$|zipcode|license|licence|passport|maiden|mrn|member_id|latitude|longitude|narrative|photo|birth_date|birthdate)($|_)')
  -- allowed: these are not identifiers of a person
  and lower(column_name) not in ('provider_org_name', 'location_name', 'payer_name', 'month_name', 'table_name', 'display', 'type_display', 'reason_display', 'value_display')

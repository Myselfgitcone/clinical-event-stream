{# A ZIP3 is three digits or null; anything longer means truncation did not happen. #}
{% test zip3_shape(model, column_name) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
  and not regexp_matches({{ column_name }}, '^[0-9]{3}$')
{% endtest %}

{# Pseudonyms are 32 hex characters (truncated HMAC-SHA256). A UUID here means a raw id leaked. #}
{% test pseudonym_shape(model, column_name) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
  and not regexp_matches({{ column_name }}, '^[0-9a-f]{32}(#[0-9]+)?$')
{% endtest %}

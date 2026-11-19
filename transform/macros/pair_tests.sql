{# Each unordered condition pair appears once. #}
{% test unique_pair(model) %}
select condition_a, condition_b, count(*) as n
from {{ model }}
group by 1, 2
having count(*) > 1
{% endtest %}

{% test bikes_within_capacity(model, column_bikes, column_capacity) %}
{#- Un nombre de vélos hors de [0, capacité] est physiquement impossible : zéro tolérance en gold. -#}
select *
from {{ model }}
where {{ column_bikes }} < 0
   or {{ column_bikes }} > {{ column_capacity }}
{% endtest %}

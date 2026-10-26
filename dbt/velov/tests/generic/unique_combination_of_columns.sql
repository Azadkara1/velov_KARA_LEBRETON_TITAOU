{% test unique_combination_of_columns(model, columns) %}
{#- Renvoie les combinaisons en double : le test échoue s'il y en a (équivalent dbt_utils, sans paquet à télécharger). -#}
select {{ columns | join(', ') }}, count(*) as n
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}

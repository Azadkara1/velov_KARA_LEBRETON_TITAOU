{#-
  Gold : table d'entraînement, au schéma du contrat (colonnes brutes + cible).

  EX-11 (pas de fuite du futur) : les colonnes d'entrée sont celles de l'heure H ;
  seule la cible `bikes_next_hour` regarde H+1, et c'est son rôle.
  La cible n'existe que si l'heure suivante est bien observée (pas de trou) : sinon on
  prendrait la valeur de "la ligne suivante", qui peut dater de 5 h plus tard.

  EX-10 (rejouable) : table recalculée entièrement à chaque build, sans now() ni aléa,
  avec un tri total -> mêmes entrées, même table.

  Les features dérivées (heure, jour, occupancy_rate) ne sont PAS recalculées ici : elles
  vivent dans velov.features, importé par l'entraînement ET l'API. Les réécrire en SQL
  créerait une 2e implémentation, donc un risque de training-serving skew.
-#}
with lagged as (
    select
        station_id,
        observed_hour,
        capacity,
        bikes_available,
        temperature,
        is_raining,
        lead(observed_hour) over w as next_hour,
        lead(bikes_available) over w as next_bikes
    from {{ ref('stg_observations') }}
    window w as (partition by station_id order by observed_hour)
)

select
    l.station_id::int as station_id,
    l.observed_hour as "timestamp",
    l.capacity::int as capacity,
    l.bikes_available::int as bikes_available,
    l.temperature::double precision as temperature,
    l.is_raining as is_raining,
    l.next_bikes::int as bikes_next_hour
from lagged l
inner join {{ ref('dim_stations') }} s using (station_id)
where l.next_hour = l.observed_hour + interval '1 hour'
order by l.station_id, l.observed_hour

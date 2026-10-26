{#-
  Silver : données nettoyées, une ligne par station et par heure.
  - instant ramené à l'heure pleine (la collecte réelle n'est jamais pile à :00) ;
  - doublons sur la même heure : on garde la dernière observation, de façon déterministe ;
  - lignes inutilisables écartées (valeur manquante, capacité <= 0, plus de vélos que de places).
  Les lignes écartées restent en bronze : rien n'est détruit, on peut les auditer.
-#}
with typed as (
    select
        station_id,
        date_trunc('hour', observed_at) as observed_hour,
        capacity,
        bikes_available,
        temperature,
        is_raining,
        observed_at,
        ingested_at
    from {{ source('bronze', 'velov_raw') }}
),

ranked as (
    select
        *,
        row_number() over (
            partition by station_id, observed_hour
            order by observed_at desc, ingested_at desc
        ) as rn
    from typed
)

select
    station_id,
    observed_hour,
    capacity,
    bikes_available,
    temperature,
    is_raining
from ranked
where rn = 1
  and capacity is not null and capacity > 0
  and bikes_available is not null and bikes_available between 0 and capacity
  and temperature is not null
  and is_raining is not null

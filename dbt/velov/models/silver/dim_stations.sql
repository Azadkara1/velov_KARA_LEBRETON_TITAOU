{#- Référentiel des stations connues (cible des tests `relationships`). -#}
select
    station_id,
    max(capacity) as capacity,
    min(observed_hour) as first_seen,
    max(observed_hour) as last_seen
from {{ ref('stg_observations') }}
group by station_id

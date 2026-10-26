{{ config(warn_if='>0', error_if='>50') }}
{#-
  Test avec SEUIL sur la source brute : quelques mesures aberrantes sont normales (capteur,
  bug ponctuel) et sont écartées en silver -> simple avertissement. Au-delà de 50 lignes,
  c'est la collecte qui est cassée (capacité à 0, colonnes inversées...) : le build échoue
  AVANT de publier quoi que ce soit.
-#}
select station_id, observed_at, capacity, bikes_available
from {{ source('bronze', 'velov_raw') }}
where capacity is null
   or capacity <= 0
   or bikes_available > capacity

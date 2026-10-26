"""Contrat de données de la table gold, vérifié par Pandera avant tout entraînement (EX-12).

Deux gardes successifs : dbt (`contract: enforced` + tests) à la fabrication de la table,
Pandera ici à la consommation. Si l'un des deux est contourné ou en retard sur l'autre,
l'entraînement ne démarre pas sur des données invalides.
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa

from velov.features import TARGET

GOLD_SCHEMA = pa.DataFrameSchema(
    {
        "station_id": pa.Column(int, pa.Check.ge(1)),
        # Fuseau UTC exigé ; l'unité (ns, us) dépend de la version de pandas, donc on ne la fige pas.
        "timestamp": pa.Column(
            checks=pa.Check(
                lambda s: isinstance(s.dtype, pd.DatetimeTZDtype) and str(s.dtype.tz) == "UTC",
                error="timestamp doit être un datetime UTC",
            )
        ),
        "capacity": pa.Column(int, pa.Check.in_range(1, 500)),
        "bikes_available": pa.Column(int, pa.Check.ge(0)),
        "temperature": pa.Column(float, pa.Check.in_range(-30, 50)),
        "is_raining": pa.Column(bool),
        TARGET: pa.Column(int, pa.Check.ge(0)),
    },
    checks=[
        pa.Check(lambda df: df["bikes_available"] <= df["capacity"], error="bikes_available > capacity"),
        pa.Check(lambda df: df[TARGET] <= df["capacity"], error=f"{TARGET} > capacity"),
        pa.Check(lambda df: ~df.duplicated(["station_id", "timestamp"]), error="doublon (station_id, timestamp)"),
    ],
    strict=True,  # une colonne en trop ou manquante = contrat violé
    coerce=False,
)


def validate_gold(df: pd.DataFrame) -> pd.DataFrame:
    """Lève `pandera.errors.SchemaErrors` listant TOUTES les violations (lazy), sinon renvoie `df`."""
    return GOLD_SCHEMA.validate(df, lazy=True)

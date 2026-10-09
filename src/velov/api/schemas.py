"""Contrat d'entrée / sortie de l'API (validé par Pydantic, publié dans OpenAPI).

TP1, partie 2 : complétez les schémas. Mode : SANS IA pour cette partie.
"""

from __future__ import annotations

from datetime import UTC

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class PredictionRequest(BaseModel):
    """Une observation de station à l'instant t.

    TODO 1 [Must] : déclarer les 6 champs attendus par le modèle (voir velov.features.RAW_COLUMNS)
             avec leur type Python. Pour timestamp, utilisez AwareDatetime et non datetime :
             datetime accepte "2026-10-06T08:00:00" sans fuseau, un instant ambigu.
    TODO 2 [Must] : ajouter des bornes avec Field(...) : station_id >= 1, 0 < capacity <= 100,
             bikes_available >= 0, température entre -30 et 50 °C.
    TODO 3 [Must] : refuser un champ inconnu (indice : model_config / extra).
    TODO 4 [Must] : refuser bikes_available > capacity (indice : @model_validator(mode="after")).
    TODO 4 bis [Should] : normaliser timestamp en UTC
             (indice : @field_validator("timestamp") et value.astimezone(UTC)).
    """

    model_config = ConfigDict(extra="forbid")

    station_id: int = Field(..., ge=1, description="Identifiant de la station")
    timestamp: AwareDatetime = Field(..., description="Instant de l'observation, avec fuseau horaire")
    capacity: int = Field(..., gt=0, le=100, description="Nombre de bornes de la station")
    bikes_available: int = Field(..., ge=0, description="Vélos disponibles à l'instant t")
    temperature: float = Field(..., ge=-30, le=50, description="Température en °C")
    is_raining: bool = Field(..., description="Pluie à l'instant t")

    @field_validator("timestamp")
    @classmethod
    def to_utc(cls, value: AwareDatetime) -> AwareDatetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def bikes_within_capacity(self) -> PredictionRequest:
        if self.bikes_available > self.capacity:
            raise ValueError("bikes_available ne peut pas dépasser capacity")
        return self


class PredictionResponse(BaseModel):
    station_id: int
    target_timestamp: AwareDatetime = Field(..., description="Instant prédit (t + 1 h)")
    predicted_bikes: float = Field(..., ge=0)
    model_version: str


# STRETCH : BatchPredictionRequest (1 à 1000 PredictionRequest) et BatchPredictionResponse

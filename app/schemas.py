"""Schémas de données : traduction Python du contrat openapi.yml."""
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# --- Listes de valeurs autorisées (enum dans le contrat) ---
class Weather(str, Enum):
    normal = "normal"
    pluie = "pluie"
    neige = "neige"
    orage = "orage"


class DeliveryZone(str, Enum):
    centre = "centre"
    proche_banlieue = "proche_banlieue"
    banlieue = "banlieue"
    rurale = "rurale"


class CustomerType(str, Enum):
    standard = "standard"
    premium = "premium"


# --- Une commande ---
class OrderFeatures(BaseModel):
    model_config = ConfigDict(
        extra="forbid",  # champ inconnu → refus (additionalProperties: false)
        strict=True,     # "14" (texte) n'est PAS converti en 14 (nombre)
    )

    order_id: str | None = Field(default=None, examples=["CMD-000001"],
                                 description="Généré par le serveur si absent.")
    hour: int = Field(ge=0, le=23, examples=[14])
    day_of_week: int = Field(ge=0, le=6, description="0 = lundi ... 6 = dimanche")
    weekend: Literal[0, 1]
    distance_km: float = Field(ge=0, examples=[3.5])
    order_value_eur: float = Field(ge=0, examples=[89.9])
    weight_kg: float = Field(ge=0, examples=[2.4])
    stock_available: Literal[0, 1]
    preparation_time_min: float = Field(ge=0, examples=[18])
    carrier_capacity: float = Field(ge=0, le=1, examples=[0.85])
    weather: Weather
    delivery_zone: DeliveryZone
    customer_type: CustomerType


# --- Réponse de /health ---
class HealthStatus(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
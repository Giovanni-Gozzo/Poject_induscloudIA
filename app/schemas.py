"""Schémas de données : traduction Python du contrat openapi.yml."""
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime

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


class OrderFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")  # champ inconnu → refus

    order_id: str | None = Field(default=None, examples=["CMD-000001"],
                                 description="Généré par le serveur si absent.")
    # strict=True sur les nombres : "14" (texte) n'est PAS converti en 14
    hour: int = Field(ge=0, le=23, strict=True, examples=[14])
    day_of_week: int = Field(ge=0, le=6, strict=True,
                             description="0 = lundi ... 6 = dimanche")
    weekend: int = Field(ge=0, le=1, strict=True)
    distance_km: float = Field(ge=0, strict=True, examples=[3.5])
    order_value_eur: float = Field(ge=0, strict=True, examples=[89.9])
    weight_kg: float = Field(ge=0, strict=True, examples=[2.4])
    stock_available: int = Field(ge=0, le=1, strict=True) 
    preparation_time_min: float = Field(ge=0, strict=True, examples=[18])
    carrier_capacity: float = Field(ge=0, le=1, strict=True, examples=[0.85])
    # Enum sans strict : le texte "normal" est accepté, "grêle" est refusé
    weather: Weather
    delivery_zone: DeliveryZone
    customer_type: CustomerType

# --- Réponse de /health ---
class HealthStatus(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str

# --- Réponse d'une prédiction ---
class Prediction(BaseModel):
    order_id: str
    express_eligible: bool
    decision: Literal["oui", "non"]
    probability: float = Field(ge=0, le=1)
    model_version: str
    predicted_at: datetime
    latency_ms: float | None = None


# --- Réponse de /health/ready ---
class ReadinessStatus(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, str]
    version: str | None = None

# --- Format unique de toutes les erreurs ---
class Error(BaseModel):
    error: str = Field(description="Code d'erreur stable, branchable côté client",
                       examples=["validation_error"])
    message: str = Field(description="Message destiné à l'humain, non contractuel")
    details: list[str] | None = None
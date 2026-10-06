"""API de prédiction d'éligibilité à la livraison express."""
from fastapi import FastAPI

from app.schemas import HealthStatus

SERVICE_NAME = "eligibilite-livraison-express"
APP_VERSION = "1.0.0"

app = FastAPI(
    title="eligibilite-livraison-express API",
    version=APP_VERSION,
    description="API de prédiction d'éligibilité à la livraison express.",
)


@app.get(
    "/health",
    tags=["health"],
    operation_id="getHealth",
    summary="Sonde de vivacité",
    response_model=HealthStatus,
)
def get_health() -> HealthStatus:
    """Répond 200 si le processus est vivant. Ne dépend d'aucune brique externe."""
    return HealthStatus(service=SERVICE_NAME, version=APP_VERSION)
"""API de prédiction d'éligibilité à la livraison express."""
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response

from app.config import APP_VERSION, MODEL_CARD_PATH, MODEL_PATH, SERVICE_NAME
from app.model import ModelService
from app.schemas import HealthStatus, OrderFeatures, Prediction, ReadinessStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(SERVICE_NAME)

model_service = ModelService(MODEL_PATH, MODEL_CARD_PATH)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ce code s'exécute UNE fois, au démarrage du serveur
    try:
        model_service.load()
    except Exception:
        # On démarre quand même : /health répondra 200, /health/ready répondra 503
        logger.exception("Le modèle n'a pas pu être chargé")
    yield
    # (ce qui serait écrit ici s'exécuterait à l'arrêt du serveur)


app = FastAPI(
    title="eligibilite-livraison-express API",
    version=APP_VERSION,
    description="API de prédiction d'éligibilité à la livraison express.",
    lifespan=lifespan,
)


def new_order_id() -> str:
    """Génère un identifiant unique, ex. CMD-3F9A1C02B7."""
    return f"CMD-{uuid.uuid4().hex[:10].upper()}"


# ----------------------------- health -----------------------------
@app.get("/health", tags=["health"], operation_id="getHealth",
         summary="Sonde de vivacité", response_model=HealthStatus)
def get_health() -> HealthStatus:
    return HealthStatus(service=SERVICE_NAME, version=APP_VERSION)


@app.get("/health/ready", tags=["health"], operation_id="getReadiness",
         summary="Sonde de disponibilité", response_model=ReadinessStatus,
         responses={503: {"model": ReadinessStatus, "description": "Le service n'est pas prêt"}})
def get_readiness(response: Response) -> ReadinessStatus:
    checks = {"model": "loaded" if model_service.is_loaded else "not_loaded"}
    ready = model_service.is_loaded
    if not ready:
        response.status_code = 503
    return ReadinessStatus(status="ready" if ready else "not_ready",
                           checks=checks, version=APP_VERSION)


# ---------------------------- predictions ----------------------------
@app.post("/v1/predictions", tags=["predictions"], operation_id="createPrediction",
          summary="Prédire l'éligibilité express d'une commande",
          response_model=Prediction)
def create_prediction(order: OrderFeatures) -> Prediction:
    if not model_service.is_loaded:
        raise HTTPException(status_code=503, detail="Modèle indisponible")
    if order.order_id is None:
        order = order.model_copy(update={"order_id": new_order_id()})
    return model_service.predict(order)
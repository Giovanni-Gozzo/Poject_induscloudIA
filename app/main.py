"""API de prédiction d'éligibilité à la livraison express."""
from datetime import datetime, timezone
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import metrics
from app.config import (API_KEYS, APP_VERSION, DATABASE_URL, DOCS_ENABLED, MODEL_CARD_PATH,
                        MODEL_PATH, RABBITMQ_QUEUE, RABBITMQ_URL, RATE_LIMIT_PER_MINUTE,
                        SERVICE_NAME)
from app.errors import (ApiError, api_error_handler, http_error_handler,
                        unhandled_error_handler, validation_error_handler)
from app.model import ModelService
from app.model_repository import FileModelRepository
from app.schemas import (BatchPredictionRequest, BatchPredictionResponse, Error, HealthStatus,
                         ModelCard, OrderAccepted, OrderFeatures, Prediction, ReadinessStatus)
from app.security import ApiKeyRegistry, Authenticator, RateLimiter, Role, parse_api_keys
from app.store import OrderStore, build_store
from app.streaming import OrderEventPublisher, build_event_publisher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(SERVICE_NAME)

model_service = ModelService(FileModelRepository(MODEL_PATH, MODEL_CARD_PATH))  # ADR-0002
store: OrderStore = build_store(DATABASE_URL)  # PostgreSQL si DATABASE_URL est défini (ADR-0001)
event_publisher: OrderEventPublisher = build_event_publisher(RABBITMQ_URL, RABBITMQ_QUEUE)
# Une variable API_KEYS mal formée fait échouer le démarrage : mieux vaut planter que s'ouvrir
auth = Authenticator(ApiKeyRegistry(parse_api_keys(API_KEYS)),
                     RateLimiter(RATE_LIMIT_PER_MINUTE))  # ADR-0007

# Codes de réponse ajoutés par la sécurité sur toutes les routes protégées
AUTH_RESPONSES = {
    401: {"model": Error, "description": "Clé d'API absente, invalide ou expirée"},
    403: {"model": Error, "description": "Rôle insuffisant"},
    429: {"model": Error, "description": "Trop de requêtes"},
}

# En-têtes ajoutés à chaque réponse (ADR-0007)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",  # le navigateur ne « devine » pas le type de contenu
    "X-Frame-Options": "DENY",            # l'API ne peut pas être affichée dans une iframe
    "Cache-Control": "no-store",          # les réponses ne restent pas dans un cache
    "Referrer-Policy": "no-referrer",
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Ce code s'exécute UNE fois, au démarrage du serveur
    try:
        model_service.load()
    except Exception:  # pylint: disable=broad-exception-caught
        # On démarre quand même : /health répondra 200, /health/ready répondra 503
        logger.exception("Le modèle n'a pas pu être chargé")
    try:
        store.setup()
    except Exception:  # pylint: disable=broad-exception-caught
        # Même principe : /health/ready répondra 503 tant que la base est injoignable
        logger.exception("Le stockage des commandes n'a pas pu être préparé")
    yield
    store.close()


app = FastAPI(
    title="eligibilite-livraison-express API",
    version=APP_VERSION,
    description="API de prédiction d'éligibilité à la livraison express.",
    lifespan=lifespan,
    # En prod, on n'expose pas la documentation de l'API (ADR-0007)
    docs_url="/docs" if DOCS_ENABLED else None,
    redoc_url=None,
    openapi_url="/openapi.json" if DOCS_ENABLED else None,
)

# Gestionnaires d'erreurs : toutes les erreurs sortent au format Error du contrat
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    return response


@app.middleware("http")
async def observe_requests(request: Request, call_next) -> Response:
    """Mesure chaque requête (séance 7) : compteur par statut + histogramme de latence."""
    start = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    endpoint = getattr(route, "path", request.url.path)  # gabarit, pas l'URL brute
    metrics.observe_request(
        request.method, endpoint, response.status_code, time.perf_counter() - start
    )
    return response


def new_order_id() -> str:
    """Génère un identifiant unique, ex. CMD-3F9A1C02B7."""
    return f"CMD-{uuid.uuid4().hex[:10].upper()}"


def with_order_id(order: OrderFeatures) -> OrderFeatures:
    """Renvoie la commande avec un order_id (généré s'il est absent)."""
    if order.order_id:
        return order
    return order.model_copy(update={"order_id": new_order_id()})


# ----------------------------- health -----------------------------
# Routes publiques : utilisées par le healthcheck Docker et Coolify, elles ne révèlent aucune donnée
@app.get("/health", tags=["health"], operation_id="getHealth",
         summary="Sonde de vivacité", response_model=HealthStatus)
def get_health() -> HealthStatus:
    return HealthStatus(service=SERVICE_NAME, version=APP_VERSION)


@app.get("/health/ready", tags=["health"], operation_id="getReadiness",
         summary="Sonde de disponibilité", response_model=ReadinessStatus,
         responses={503: {"model": ReadinessStatus, "description": "Le service n'est pas prêt"}})
def get_readiness(response: Response) -> ReadinessStatus:
    checks = {
        "model": "loaded" if model_service.is_loaded else "not_loaded",
        "order_store": "reachable" if store.ping() else "unreachable",
    }
    ready = checks["model"] == "loaded" and checks["order_store"] == "reachable"
    if not ready:
        response.status_code = 503
    return ReadinessStatus(status="ready" if ready else "not_ready",
                           checks=checks, version=APP_VERSION)


# ------------------------------ orders ------------------------------
def build_order_event(order: OrderFeatures, prediction: Prediction) -> dict:
    """Construit l'événement OrderEvent (openapi.yml) + prédiction pour le logisticien."""
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "order.created",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
        "order": order.model_dump(mode="json"),
        "prediction": prediction.model_dump(mode="json"),
    }


def predict_and_store(order: OrderFeatures) -> None:
    """Tâche d'arrière-plan : calcule la prédiction APRÈS la réponse 202."""
    if not model_service.is_loaded:
        logger.warning("Commande %s non prédite : modèle indisponible", order.order_id)
        return
    prediction = model_service.predict(order)
    metrics.record_prediction(prediction.decision)
    store.save_prediction(prediction)
    event_publisher.publish(build_order_event(order, prediction))
    logger.info("Commande %s prédite : %s (%.4f)",
                order.order_id, prediction.decision, prediction.probability)


@app.post("/v1/orders", tags=["orders"], operation_id="createOrder",
          summary="Enregistrer une commande à prédire",
          status_code=202, response_model=OrderAccepted,
          dependencies=[Depends(auth.require(Role.user))],
          responses={422: {"model": Error, "description": "Commande invalide"},
                     500: {"model": Error, "description": "Erreur interne"},
                     **AUTH_RESPONSES})
def create_order(order: OrderFeatures, background_tasks: BackgroundTasks) -> OrderAccepted:
    order = with_order_id(order)
    store.save_order(order)                               # 1. on range la commande
    background_tasks.add_task(predict_and_store, order)   # 2. on programme la prédiction
    return OrderAccepted(order_id=order.order_id)         # 3. on rend le ticket tout de suite


# Relire une commande donne accès aux données clients : réservé aux admins (ADR-0007)
@app.get("/v1/orders/{order_id}", tags=["orders"], operation_id="getOrder",
         summary="Relire une commande collectée", response_model=OrderFeatures,
         dependencies=[Depends(auth.require(Role.admin))],
         responses={404: {"model": Error, "description": "Commande inconnue"},
                    **AUTH_RESPONSES})
def get_order(order_id: str) -> OrderFeatures:
    order = store.get_order(order_id)
    if order is None:
        raise ApiError(404, "order_not_found", f"Commande inconnue : {order_id}")
    return order


# ---------------------------- predictions ----------------------------
@app.post("/v1/predictions", tags=["predictions"], operation_id="createPrediction",
          summary="Prédire l'éligibilité express d'une commande",
          response_model=Prediction,
          dependencies=[Depends(auth.require(Role.user))],
          responses={422: {"model": Error, "description": "Commande invalide"},
                     503: {"model": Error, "description": "Modèle indisponible"},
                     **AUTH_RESPONSES})
def create_prediction(order: OrderFeatures, background_tasks: BackgroundTasks) -> Prediction:
    if not model_service.is_loaded:
        raise ApiError(503, "model_unavailable", "Le modèle n'est pas chargé")
    order_with_id = with_order_id(order)
    prediction = model_service.predict(order_with_id)
    metrics.record_prediction(prediction.decision)
    store.save_prediction(prediction)  # garde une trace (utile à la séance 5)
    # Publication APRÈS la réponse : un broker lent ou absent ne ralentit pas le client (TP6)
    background_tasks.add_task(event_publisher.publish, build_order_event(order_with_id, prediction))
    return prediction


@app.post("/v1/predictions/batch", tags=["predictions"], operation_id="createBatchPredictions",
          summary="Prédire un lot de commandes",
          response_model=BatchPredictionResponse,
          dependencies=[Depends(auth.require(Role.user))],
          responses={422: {"model": Error, "description": "Lot invalide"},
                     503: {"model": Error, "description": "Modèle indisponible"},
                     **AUTH_RESPONSES})
def create_batch_predictions(
    payload: BatchPredictionRequest,
    background_tasks: BackgroundTasks,
) -> BatchPredictionResponse:
    if not model_service.is_loaded:
        raise ApiError(503, "model_unavailable", "Le modèle n'est pas chargé")
    orders = [with_order_id(order) for order in payload.orders]
    predictions = model_service.predict_batch(orders)
    for order, prediction in zip(orders, predictions):
        metrics.record_prediction(prediction.decision)
        store.save_prediction(prediction)
        background_tasks.add_task(event_publisher.publish, build_order_event(order, prediction))
    return BatchPredictionResponse(predictions=predictions, count=len(predictions))


@app.get("/v1/predictions/{order_id}", tags=["predictions"], operation_id="getPrediction",
         summary="Relire une prédiction déjà calculée",
         response_model=Prediction,
         dependencies=[Depends(auth.require(Role.user))],
         responses={404: {"model": Error, "description": "Prédiction inconnue"},
                    **AUTH_RESPONSES})
def get_prediction(order_id: str) -> Prediction:
    prediction = store.get_prediction(order_id)
    if prediction is None:
        raise ApiError(404, "prediction_not_found", f"Prédiction inconnue : {order_id}")
    return prediction


# ------------------------------- model -------------------------------
@app.get("/v1/model", tags=["model"], operation_id="getModelCard",
         summary="Métadonnées et métriques du modèle en service",
         response_model=ModelCard,
         dependencies=[Depends(auth.require(Role.user))],
         responses={503: {"model": Error, "description": "Modèle indisponible"},
                    **AUTH_RESPONSES})
def get_model_card() -> ModelCard:
    if not model_service.is_loaded:
        raise ApiError(503, "model_unavailable", "Le modèle n'est pas chargé")
    return ModelCard(**model_service.card)


# ------------------------------ metrics ------------------------------
# Endpoint public de scrape (réseau interne) : format texte Prometheus, pas du JSON (séance 7)
@app.get("/metrics", tags=["metrics"], operation_id="getMetrics",
         summary="Métriques exposées au format Prometheus",
         response_class=PlainTextResponse,
         responses={200: {"description": "Métriques au format d'exposition Prometheus",
                          "content": {"text/plain": {"schema": {"type": "string"}}}}})
def get_metrics() -> Response:
    metrics.update_model_state(
        model_service.is_loaded,
        model_service.card.get("model_version") if model_service.is_loaded else None,
    )
    payload, content_type = metrics.render()
    return Response(content=payload, media_type=content_type)

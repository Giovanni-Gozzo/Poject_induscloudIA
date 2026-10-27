"""API de prédiction d'éligibilité à la livraison express."""
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import (API_KEYS, APP_VERSION, DATABASE_URL, DOCS_ENABLED, MODEL_CARD_PATH,
                        MODEL_PATH, RATE_LIMIT_PER_MINUTE, SERVICE_NAME)
from app.errors import (ApiError, api_error_handler, http_error_handler,
                        unhandled_error_handler, validation_error_handler)
from app.model import ModelService
from app.model_repository import FileModelRepository
from app.schemas import (Error, HealthStatus, OrderAccepted, OrderFeatures,
                         Prediction, ReadinessStatus)
from app.security import ApiKeyRegistry, Authenticator, RateLimiter, Role, parse_api_keys
from app.store import OrderStore, build_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(SERVICE_NAME)

model_service = ModelService(FileModelRepository(MODEL_PATH, MODEL_CARD_PATH))  # ADR-0002
store: OrderStore = build_store(DATABASE_URL)  # PostgreSQL si DATABASE_URL est défini (ADR-0001)
# Une variable API_KEYS mal formée fait échouer le démarrage : mieux vaut planter que s'ouvrir
auth = Authenticator(ApiKeyRegistry(parse_api_keys(API_KEYS)),
                     RateLimiter(RATE_LIMIT_PER_MINUTE))  # ADR-0007

# Codes de réponse ajoutés par la sécurité sur toutes les routes protégées
AUTH_RESPONSES = {
    401: {"model": Error, "description": "Clé d'API absente, invalide ou expirée"},
    403: {"model": Error, "description": "Rôle insuffisant"},
    429: {"model": Error, "description": "Trop de requêtes"},
}

# En-têtes ajoutés à chaque réponse (ADR-0006)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",  # le navigateur ne « devine » pas le type de contenu
    "X-Frame-Options": "DENY",            # l'API ne peut pas être affichée dans une iframe
    "Cache-Control": "no-store",          # les réponses ne restent pas dans un cache
    "Referrer-Policy": "no-referrer",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ce code s'exécute UNE fois, au démarrage du serveur
    try:
        model_service.load()
    except Exception:
        # On démarre quand même : /health répondra 200, /health/ready répondra 503
        logger.exception("Le modèle n'a pas pu être chargé")
    try:
        store.setup()
    except Exception:
        # Même principe : /health/ready répondra 503 tant que la base est injoignable
        logger.exception("Le stockage des commandes n'a pas pu être préparé")
    yield
    store.close()


app = FastAPI(
    title="eligibilite-livraison-express API",
    version=APP_VERSION,
    description="API de prédiction d'éligibilité à la livraison express.",
    lifespan=lifespan,
    # En prod, on n'expose pas la documentation de l'API (ADR-0006)
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
def predict_and_store(order: OrderFeatures) -> None:
    """Tâche d'arrière-plan : calcule la prédiction APRÈS la réponse 202."""
    if not model_service.is_loaded:
        logger.warning("Commande %s non prédite : modèle indisponible", order.order_id)
        return
    prediction = model_service.predict(order)
    store.save_prediction(prediction)
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
def create_prediction(order: OrderFeatures) -> Prediction:
    if not model_service.is_loaded:
        raise ApiError(503, "model_unavailable", "Le modèle n'est pas chargé")
    prediction = model_service.predict(with_order_id(order))
    store.save_prediction(prediction)  # garde une trace (utile à la séance 5)
    return prediction

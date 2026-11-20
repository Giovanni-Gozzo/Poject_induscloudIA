"""Métriques d'observabilité exposées au format Prometheus (séance 7, ADR-0008).

Les compteurs vivent en mémoire du processus et sont lus par un scrape de
``GET /metrics``. Aucune brique externe n'est nécessaire pour démarrer.
"""
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

HTTP_REQUESTS_TOTAL = Counter(
    "delivery_http_requests_total",
    "Nombre de requêtes HTTP traitées.",
    ["method", "endpoint", "status"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "delivery_http_request_duration_seconds",
    "Durée des requêtes HTTP, en secondes.",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
PREDICTIONS_TOTAL = Counter(
    "delivery_predictions_total",
    "Nombre de prédictions calculées, par décision.",
    ["decision"],
)
MODEL_LOADED = Gauge(
    "delivery_model_loaded",
    "1 si le modèle est chargé et prêt à prédire, sinon 0.",
)
MODEL_INFO = Gauge(
    "delivery_model_info",
    "Version du modèle en service (valeur toujours 1).",
    ["version"],
)


def observe_request(method: str, endpoint: str, status: int, duration_seconds: float) -> None:
    """Enregistre une requête HTTP : compteur par statut et histogramme de latence."""
    HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status=str(status)).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, endpoint=endpoint).observe(duration_seconds)


def record_prediction(decision: str) -> None:
    """Incrémente le compteur de prédictions pour la décision ``oui`` ou ``non``."""
    PREDICTIONS_TOTAL.labels(decision=decision).inc()


def update_model_state(loaded: bool, version: str | None) -> None:
    """Met à jour les jauges d'état du modèle avant un scrape."""
    MODEL_LOADED.set(1 if loaded else 0)
    if version:
        MODEL_INFO.labels(version=version).set(1)


def render() -> tuple[bytes, str]:
    """Renvoie le texte d'exposition Prometheus et son type de contenu."""
    return generate_latest(), CONTENT_TYPE_LATEST

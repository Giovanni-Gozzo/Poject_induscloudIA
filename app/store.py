"""Stockage des commandes et des prédictions."""
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from threading import Lock

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.schemas import OrderFeatures, Prediction

logger = logging.getLogger(__name__)

SCHEMA_SQL = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
POOL_MIN_SIZE = 1
POOL_MAX_SIZE = 5
CONNECTION_TIMEOUT_S = 5  # temps max pour obtenir une connexion du pool


class OrderStore(ABC):
    """Les RÈGLES : ce que tout placard doit savoir faire."""

    def setup(self) -> None:
        """Prépare le placard au démarrage de l'API (rien à faire par défaut)."""

    def close(self) -> None:
        """Libère les ressources à l'arrêt de l'API (rien à faire par défaut)."""

    @abstractmethod
    def save_order(self, order: OrderFeatures) -> None: ...

    @abstractmethod
    def get_order(self, order_id: str) -> OrderFeatures | None: ...

    @abstractmethod
    def save_prediction(self, prediction: Prediction) -> None: ...

    @abstractmethod
    def get_prediction(self, order_id: str) -> Prediction | None: ...

    @abstractmethod
    def ping(self) -> bool: ...


class InMemoryOrderStore(OrderStore):
    """Un placard EN MÉMOIRE : simple, mais vidé à chaque redémarrage."""

    def __init__(self) -> None:
        self._orders = {}       # dictionnaire : order_id → commande
        self._predictions = {}  # dictionnaire : order_id → prédiction
        self._lock = Lock()

    def save_order(self, order: OrderFeatures) -> None:
        with self._lock:
            self._orders[order.order_id] = order

    def get_order(self, order_id: str) -> OrderFeatures | None:
        return self._orders.get(order_id)

    def save_prediction(self, prediction: Prediction) -> None:
        with self._lock:
            self._predictions[prediction.order_id] = prediction

    def get_prediction(self, order_id: str) -> Prediction | None:
        return self._predictions.get(order_id)

    def ping(self) -> bool:
        return True  # la mémoire est toujours accessible


class PostgresOrderStore(OrderStore):
    """Un placard DURABLE dans PostgreSQL : survit aux redémarrages (ADR-0001)."""

    def __init__(self, database_url: str) -> None:
        # open=False : aucune connexion n'est ouverte avant setup()
        self._pool = ConnectionPool(
            database_url, min_size=POOL_MIN_SIZE, max_size=POOL_MAX_SIZE, open=False
        )
        self._schema_ready = False

    def setup(self) -> None:
        self._pool.open()
        with self._pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
            self._ensure_schema(conn)

    def close(self) -> None:
        self._pool.close()

    def _ensure_schema(self, conn) -> None:
        """Crée les tables si besoin (une seule fois par démarrage réussi)."""
        if not self._schema_ready:
            conn.execute(SCHEMA_SQL)
            self._schema_ready = True
            logger.info("Schéma PostgreSQL prêt")

    def save_order(self, order: OrderFeatures) -> None:
        with self._pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
            conn.execute(
                """INSERT INTO orders (order_id, features) VALUES (%s, %s)
                   ON CONFLICT (order_id) DO UPDATE SET features = EXCLUDED.features""",
                (order.order_id, Jsonb(order.model_dump(mode="json"))),
            )

    def get_order(self, order_id: str) -> OrderFeatures | None:
        with self._pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
            row = conn.execute(
                "SELECT features FROM orders WHERE order_id = %s", (order_id,)
            ).fetchone()
        return OrderFeatures.model_validate(row[0]) if row else None

    def save_prediction(self, prediction: Prediction) -> None:
        with self._pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
            conn.execute(
                """INSERT INTO predictions (order_id, express_eligible, decision, probability,
                                            model_version, predicted_at, latency_ms)
                   VALUES (%(order_id)s, %(express_eligible)s, %(decision)s, %(probability)s,
                           %(model_version)s, %(predicted_at)s, %(latency_ms)s)
                   ON CONFLICT (order_id) DO UPDATE SET
                       express_eligible = EXCLUDED.express_eligible,
                       decision = EXCLUDED.decision,
                       probability = EXCLUDED.probability,
                       model_version = EXCLUDED.model_version,
                       predicted_at = EXCLUDED.predicted_at,
                       latency_ms = EXCLUDED.latency_ms""",
                prediction.model_dump(),
            )

    def get_prediction(self, order_id: str) -> Prediction | None:
        with self._pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
            row = conn.execute(
                """SELECT order_id, express_eligible, decision, probability,
                          model_version, predicted_at, latency_ms
                   FROM predictions WHERE order_id = %s""",
                (order_id,),
            ).fetchone()
        if row is None:
            return None
        fields = ("order_id", "express_eligible", "decision", "probability",
                  "model_version", "predicted_at", "latency_ms")
        return Prediction(**dict(zip(fields, row)))

    def ping(self) -> bool:
        """Vérifie la base ; crée le schéma s'il manque (base indisponible au démarrage)."""
        try:
            with self._pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
                self._ensure_schema(conn)
                conn.execute("SELECT 1")
            return True
        except Exception:
            logger.warning("PostgreSQL injoignable", exc_info=True)
            return False


def build_store(database_url: str | None) -> OrderStore:
    """PostgreSQL si DATABASE_URL est défini, sinon la mémoire (dev et tests)."""
    if database_url:
        return PostgresOrderStore(database_url)
    return InMemoryOrderStore()
"""Stockage des commandes et des prédictions."""
from abc import ABC, abstractmethod
from threading import Lock

from app.schemas import OrderFeatures, Prediction


class OrderStore(ABC):
    """Les RÈGLES : ce que tout placard doit savoir faire."""

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
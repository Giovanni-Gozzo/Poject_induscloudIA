"""Accès aux données de commandes pour l'entraînement (ADR-0006).

Définit l'abstraction OrderRepository (save, get, get_all) et ses implémentations :
- InMemoryOrderRepository : pour les tests unitaires et le développement sans base ;
- MongoOrderRepository : connexion à la base analytique MongoDB (pymongo).
"""
from abc import ABC, abstractmethod
from threading import Lock
from typing import Any

from pymongo import MongoClient


class OrderRepository(ABC):
    """Contrat d'accès aux commandes utilisées pour l'entraînement."""

    def close(self) -> None:
        """Libère les ressources éventuelles (rien à faire par défaut)."""

    @abstractmethod
    def save(self, order: dict[str, Any]) -> None:
        """Enregistre ou met à jour une commande (identifiée par order_id)."""

    @abstractmethod
    def get(self, order_id: str) -> dict[str, Any] | None:
        """Retourne une commande par son identifiant, ou None si absente."""

    @abstractmethod
    def get_all(self) -> list[dict[str, Any]]:
        """Retourne toutes les commandes disponibles pour l'entraînement."""


class InMemoryOrderRepository(OrderRepository):
    """Implémentation en mémoire pour les tests et le développement local."""

    def __init__(self, initial_orders: list[dict[str, Any]] | None = None) -> None:
        self._orders: dict[str, dict[str, Any]] = {}
        self._lock = Lock()
        for order in initial_orders or []:
            self.save(order)

    def save(self, order: dict[str, Any]) -> None:
        order_id = order.get("order_id")
        if not order_id:
            raise ValueError("Une commande doit contenir un champ 'order_id'.")
        with self._lock:
            self._orders[str(order_id)] = dict(order)

    def get(self, order_id: str) -> dict[str, Any] | None:
        with self._lock:
            found = self._orders.get(order_id)
            return dict(found) if found is not None else None

    def get_all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(order) for order in self._orders.values()]


class MongoOrderRepository(OrderRepository):
    """Implémentation MongoDB sur la base analytique (ADR-0006)."""

    def __init__(
        self,
        uri: str = "mongodb://localhost:27017",
        db_name: str = "livraison_express",
        collection_name: str = "orders",
        client: Any | None = None,
    ) -> None:
        self._client = client if client is not None else MongoClient(uri, serverSelectionTimeoutMS=5000)
        self._owns_client = client is None
        self._collection = self._client[db_name][collection_name]

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def save(self, order: dict[str, Any]) -> None:
        order_id = order.get("order_id")
        if not order_id:
            raise ValueError("Une commande doit contenir un champ 'order_id'.")
        doc = dict(order)
        doc.pop("_id", None)
        self._collection.replace_one({"order_id": order_id}, doc, upsert=True)

    def get(self, order_id: str) -> dict[str, Any] | None:
        doc = self._collection.find_one({"order_id": order_id}, {"_id": 0})
        return dict(doc) if doc is not None else None

    def get_all(self) -> list[dict[str, Any]]:
        return [dict(doc) for doc in self._collection.find({}, {"_id": 0})]


def build_order_repository(
    mongo_uri: str | None = None,
    db_name: str = "livraison_express",
    collection_name: str = "orders",
) -> OrderRepository:
    """Retourne MongoOrderRepository si mongo_uri est défini, sinon InMemoryOrderRepository."""
    if mongo_uri:
        return MongoOrderRepository(uri=mongo_uri, db_name=db_name, collection_name=collection_name)
    return InMemoryOrderRepository()

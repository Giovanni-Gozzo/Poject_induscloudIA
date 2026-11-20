"""Consommateur RabbitMQ pour les commandes à livrer dans la journée (TP6)."""
import json
import logging
import os
import time
from collections import deque
from threading import Event, Lock
from typing import Any

import pika

from app.streaming import DEFAULT_QUEUE_NAME

logger = logging.getLogger(__name__)


class OrderQueueState:
    """État thread-safe des livraisons reçues par le logisticien."""

    def __init__(self, max_items: int = 200) -> None:
        self._orders: deque[dict[str, Any]] = deque(maxlen=max_items)
        self._prepared: set[str] = set()
        self._lock = Lock()

    def add_event(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._orders.appendleft(dict(event))

    def mark_prepared(self, order_id: str) -> bool:
        with self._lock:
            if not any(item.get("order_id") == order_id for item in self._orders):
                return False
            self._prepared.add(order_id)
            return True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            items = [
                {**item, "prepared": item.get("order_id") in self._prepared}
                for item in self._orders
            ]
            express_count = sum(1 for item in items if item.get("express_eligible"))
            prepared_count = sum(1 for item in items if item["prepared"])
            return {
                "total": len(items),
                "express_count": express_count,
                "standard_count": len(items) - express_count,
                "prepared_count": prepared_count,
                "orders": items,
            }


def parse_order_event(raw_body: bytes | str) -> dict[str, Any] | None:
    """Décode un message JSON reçu depuis RabbitMQ (OrderEvent ou format plat)."""
    try:
        text = raw_body.decode("utf-8") if isinstance(raw_body, bytes) else raw_body
        data = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Message RabbitMQ invalide ignoré")
        return None
    if not isinstance(data, dict):
        logger.warning("Message RabbitMQ non-objet ignoré")
        return None

    # Contrat OrderEvent (openapi.yml) : {"event_id": ..., "order": {...}, "prediction": {...}}
    if isinstance(data.get("order"), dict):
        order = data["order"]
        pred = data.get("prediction") if isinstance(data.get("prediction"), dict) else {}
        order_id = pred.get("order_id") or order.get("order_id")
        if not order_id:
            logger.warning("Message OrderEvent sans order_id ignoré")
            return None
        return {
            "order_id": order_id,
            "express_eligible": pred.get("express_eligible"),
            "decision": pred.get("decision", "inconnu"),
            "probability": pred.get("probability"),
            "delivery_zone": order.get("delivery_zone"),
            "distance_km": order.get("distance_km"),
            "weight_kg": order.get("weight_kg"),
            "weather": order.get("weather"),
            "customer_type": order.get("customer_type"),
            "predicted_at": pred.get("predicted_at") or data.get("occurred_at"),
        }

    if "order_id" not in data:
        logger.warning("Message RabbitMQ sans order_id ignoré")
        return None
    return data


def consume_forever(
    rabbitmq_url: str,
    state: OrderQueueState,
    queue_name: str = DEFAULT_QUEUE_NAME,
    stop_event: Event | None = None,
) -> None:
    """Écoute la file RabbitMQ en boucle (à lancer dans un thread ou en CLI)."""
    while stop_event is None or not stop_event.is_set():
        connection = None
        try:
            connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
            channel = connection.channel()
            channel.queue_declare(
                queue=queue_name,
                durable=True,
                arguments={"x-queue-type": "quorum"},
            )

            def _on_message(ch, method, _properties, body) -> None:
                event = parse_order_event(body)
                if event is not None:
                    state.add_event(event)
                    logger.info(
                        "[Logisticien] Commande %s reçue (express=%s, zone=%s)",
                        event.get("order_id"),
                        event.get("decision"),
                        event.get("delivery_zone"),
                    )
                ch.basic_ack(delivery_tag=method.delivery_tag)

            channel.basic_qos(prefetch_count=10)
            channel.basic_consume(queue=queue_name, on_message_callback=_on_message)
            logger.info("[Consumer] En attente de commandes sur '%s'...", queue_name)
            channel.start_consuming()
        except Exception:  # pylint: disable=broad-exception-caught
            if stop_event is not None and stop_event.is_set():
                break
            logger.warning("Connexion RabbitMQ perdue, nouvelle tentative dans 3s...", exc_info=True)
            time.sleep(3)
        finally:
            if connection is not None and connection.is_open:
                connection.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    queue_name = os.getenv("RABBITMQ_QUEUE", DEFAULT_QUEUE_NAME)
    consume_forever(rabbitmq_url, OrderQueueState(), queue_name=queue_name)


if __name__ == "__main__":
    main()

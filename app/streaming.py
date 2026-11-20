"""Publication d'événements de commandes vers RabbitMQ (TP6 - Streaming)."""
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import pika

logger = logging.getLogger(__name__)

DEFAULT_QUEUE_NAME = "delivery_orders"


class OrderEventPublisher(ABC):
    """Contrat de publication d'événements de prédiction/commande."""

    @abstractmethod
    def publish(self, event: dict[str, Any]) -> None:
        """Publie un événement vers le système de streaming."""


class NoOpOrderEventPublisher(OrderEventPublisher):
    """Implémentation neutre quand RabbitMQ n'est pas configuré (tests / dev sans broker)."""

    def publish(self, event: dict[str, Any]) -> None:
        return


class RabbitMQOrderEventPublisher(OrderEventPublisher):
    """Publie les événements sur une file RabbitMQ durable de type quorum (AMQP)."""

    def __init__(self, rabbitmq_url: str, queue_name: str = DEFAULT_QUEUE_NAME) -> None:
        self._rabbitmq_url = rabbitmq_url
        self._queue_name = queue_name

    def publish(self, event: dict[str, Any]) -> None:
        connection = None
        try:
            params = pika.URLParameters(self._rabbitmq_url)
            params.socket_timeout = 3
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.queue_declare(
                queue=self._queue_name,
                durable=True,
                arguments={"x-queue-type": "quorum"},
            )
            channel.basic_publish(
                exchange="",
                routing_key=self._queue_name,
                body=json.dumps(event, default=str),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json",
                ),
            )
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning(
                "Impossible de publier l'événement %s vers RabbitMQ",
                event.get("order_id"),
                exc_info=True,
            )
        finally:
            if connection is not None and connection.is_open:
                connection.close()


def build_event_publisher(
    rabbitmq_url: str | None,
    queue_name: str = DEFAULT_QUEUE_NAME,
) -> OrderEventPublisher:
    """Retourne RabbitMQOrderEventPublisher si RABBITMQ_URL est défini, sinon NoOp."""
    if rabbitmq_url:
        return RabbitMQOrderEventPublisher(rabbitmq_url, queue_name=queue_name)
    return NoOpOrderEventPublisher()

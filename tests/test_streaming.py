"""Tests du système de streaming RabbitMQ et de l'interface logisticien (TP6)."""
from datetime import datetime, timezone
import json
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.main import build_order_event
from app.schemas import OrderEvent, OrderFeatures, Prediction
from app.streaming import (
    NoOpOrderEventPublisher,
    RabbitMQOrderEventPublisher,
    build_event_publisher,
)
from streaming.consumer import OrderQueueState, parse_order_event
from streaming.logistician_ui import app as logistician_app
from streaming.logistician_ui import queue_state


def test_build_event_publisher_selects_implementation():
    assert isinstance(build_event_publisher(None), NoOpOrderEventPublisher)
    assert isinstance(
        build_event_publisher("amqp://guest:guest@localhost:5672/"),
        RabbitMQOrderEventPublisher,
    )


def test_noop_publisher_does_not_fail():
    NoOpOrderEventPublisher().publish({"order_id": "CMD-001"})


def test_rabbitmq_publisher_declares_quorum_queue_and_publishes(monkeypatch):
    mock_channel = MagicMock()
    mock_conn = MagicMock(is_open=True)
    mock_conn.channel.return_value = mock_channel
    monkeypatch.setattr("app.streaming.pika.BlockingConnection", lambda _params: mock_conn)

    publisher = RabbitMQOrderEventPublisher("amqp://guest:guest@localhost:5672/")
    event = {"order_id": "CMD-STREAM-1", "express_eligible": True, "decision": "oui"}
    publisher.publish(event)

    mock_channel.queue_declare.assert_called_once_with(
        queue="delivery_orders",
        durable=True,
        arguments={"x-queue-type": "quorum"},
    )
    mock_channel.basic_publish.assert_called_once()
    kwargs = mock_channel.basic_publish.call_args.kwargs
    assert kwargs["routing_key"] == "delivery_orders"
    assert json.loads(kwargs["body"]) == event
    mock_conn.close.assert_called_once()


def test_rabbitmq_publisher_handles_connection_error_gracefully(monkeypatch):
    def _fail(_params):
        raise ConnectionError("broker down")

    monkeypatch.setattr("app.streaming.pika.BlockingConnection", _fail)
    publisher = RabbitMQOrderEventPublisher("amqp://guest:guest@localhost:5672/")
    publisher.publish({"order_id": "CMD-FAIL"})


def test_parse_order_event_valid_and_invalid():
    valid = parse_order_event(b'{"order_id": "CMD-1", "decision": "oui"}')
    assert valid == {"order_id": "CMD-1", "decision": "oui"}
    assert parse_order_event(b"not-json") is None
    assert parse_order_event(b"[]") is None
    assert parse_order_event(b'{"decision": "oui"}') is None


def test_build_order_event_respects_openapi_contract():
    order = OrderFeatures(
        order_id="CMD-EVT-1", hour=14, day_of_week=2, weekend=0, distance_km=3.5,
        order_value_eur=89.9, weight_kg=2.4, stock_available=1, preparation_time_min=18,
        carrier_capacity=0.85, weather="normal", delivery_zone="centre", customer_type="premium",
    )
    pred = Prediction(
        order_id="CMD-EVT-1", express_eligible=True, decision="oui",
        probability=0.9, model_version="1.0.0", predicted_at=datetime.now(timezone.utc),
    )
    raw = build_order_event(order, pred)
    OrderEvent.model_validate(raw)  # conforme au schéma OrderEvent de openapi.yml

    parsed = parse_order_event(json.dumps(raw))
    assert parsed is not None
    assert parsed["order_id"] == "CMD-EVT-1"
    assert parsed["decision"] == "oui"
    assert parsed["delivery_zone"] == "centre"


def test_order_queue_state_and_logistician_ui():
    state = OrderQueueState()
    state.add_event({"order_id": "CMD-10", "express_eligible": True, "decision": "oui"})
    state.add_event({"order_id": "CMD-11", "express_eligible": False, "decision": "non"})

    assert state.mark_prepared("CMD-10") is True
    assert state.mark_prepared("INCONNU") is False

    snap = state.snapshot()
    assert snap["total"] == 2
    assert snap["express_count"] == 1
    assert snap["standard_count"] == 1
    assert snap["prepared_count"] == 1

    queue_state.add_event({
        "order_id": "CMD-UI-1",
        "express_eligible": True,
        "decision": "oui",
        "probability": 0.91,
        "delivery_zone": "centre",
        "distance_km": 2.5,
        "weight_kg": 1.2,
        "weather": "normal",
        "customer_type": "premium",
    })
    with TestClient(logistician_app) as client:
        assert client.get("/").status_code == 200
        res = client.get("/api/orders")
        assert res.status_code == 200
        assert any(o["order_id"] == "CMD-UI-1" for o in res.json()["orders"])

        prep = client.post("/api/orders/CMD-UI-1/prepare")
        assert prep.status_code == 200
        assert prep.json() == {"order_id": "CMD-UI-1", "prepared": True}
        assert client.post("/api/orders/INCONNU/prepare").status_code == 404

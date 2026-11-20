"""Simulateur de flux de commandes vers RabbitMQ pour tester l'interface logisticien (TP6).

Usage :
    python -m streaming.producer_demo --count 10 --interval 1.0
"""
import argparse
import os
import time
import uuid
from datetime import datetime, timezone

from app.streaming import DEFAULT_QUEUE_NAME, RabbitMQOrderEventPublisher
from training.data import generate_orders_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Envoie des événements de commandes dans RabbitMQ.")
    parser.add_argument("--url", default=os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"))
    parser.add_argument("--queue", default=os.getenv("RABBITMQ_QUEUE", DEFAULT_QUEUE_NAME))
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval", type=float, default=1.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = generate_orders_dataset(n_rows=args.count)
    publisher = RabbitMQOrderEventPublisher(args.url, queue_name=args.queue)

    for _, row in df.iterrows():
        eligible = bool(row["express_eligible"])
        now = datetime.now(timezone.utc).isoformat()
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "order.created",
            "occurred_at": now,
            "schema_version": 1,
            "order": {
                "order_id": row["order_id"],
                "hour": int(row["hour"]),
                "day_of_week": int(row["day_of_week"]),
                "weekend": int(row["weekend"]),
                "distance_km": float(row["distance_km"]),
                "order_value_eur": float(row["order_value_eur"]),
                "weight_kg": float(row["weight_kg"]),
                "stock_available": int(row["stock_available"]),
                "preparation_time_min": float(row["preparation_time_min"]),
                "carrier_capacity": float(row["carrier_capacity"]),
                "weather": row["weather"],
                "delivery_zone": row["delivery_zone"],
                "customer_type": row["customer_type"],
            },
            "prediction": {
                "order_id": row["order_id"],
                "express_eligible": eligible,
                "decision": "oui" if eligible else "non",
                "probability": 0.87 if eligible else 0.24,
                "model_version": "1.0.0",
                "predicted_at": now,
            },
        }
        publisher.publish(event)
        print(f"[Publisher] Événement envoyé : {row['order_id']} ({'oui' if eligible else 'non'})")
        if args.interval > 0:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()

"""Peuple la base analytique MongoDB avec des commandes pour tester le TP4.

Usage :
    python -m scripts.seed_mongo --uri mongodb://localhost:27017 --rows 600
"""
import argparse
import os

from training.data import generate_orders_dataset
from training.repository import MongoOrderRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialise MongoDB avec des commandes d'entraînement.")
    parser.add_argument("--uri", default=os.getenv("MONGO_URI", "mongodb://localhost:27017"))
    parser.add_argument("--db", default=os.getenv("MONGO_DB", "livraison_express"))
    parser.add_argument("--collection", default=os.getenv("MONGO_COLLECTION", "orders"))
    parser.add_argument("--rows", type=int, default=600)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = generate_orders_dataset(n_rows=args.rows)
    df["order_date"] = df["order_date"].dt.strftime("%Y-%m-%dT%H:%M:%S")

    repo = MongoOrderRepository(uri=args.uri, db_name=args.db, collection_name=args.collection)
    try:
        records = df.to_dict(orient="records")
        for record in records:
            repo.save(record)
        print(f"{len(records)} commandes enregistrées dans {args.db}.{args.collection}.")
    finally:
        repo.close()


if __name__ == "__main__":
    main()

"""Pipeline d'orchestration du réentraînement du modèle (TP4).

L'entraînement est un processus d'exécution (et non de construction CI/CD) :
1. Extraction des commandes depuis OrderRepository (MongoDB analytique, ADR-0006).
2. Vérification du volume minimal de données.
3. Nettoyage, validation, entraînement et suivi MLflow.
4. Contrôle qualité (ROC-AUC minimal) avant publication des artefacts.
"""
import argparse
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from training.repository import OrderRepository, build_order_repository
from training.train import (
    ARTIFACTS_DIR,
    build_model_card,
    save_artifacts,
    split_orders,
    train_and_track,
)

logger = logging.getLogger(__name__)

DEFAULT_MIN_ORDERS = 200
DEFAULT_MIN_ROC_AUC = 0.70


@dataclass(frozen=True)
class RetrainResult:
    """Résultat d'une exécution du pipeline de réentraînement."""

    promoted: bool
    reason: str
    order_count: int
    metrics: dict[str, float] | None = None
    run_id: str | None = None


def run_retrain_pipeline(
    repository: OrderRepository,
    artifacts_dir: Path = ARTIFACTS_DIR,
    min_orders: int = DEFAULT_MIN_ORDERS,
    min_roc_auc: float = DEFAULT_MIN_ROC_AUC,
) -> RetrainResult:
    """Exécute le réentraînement complet avec garde-fou sur le volume et les métriques."""
    orders = repository.get_all()  # une seule lecture de la base
    order_count = len(orders)
    if order_count < min_orders:
        reason = f"Volume insuffisant pour réentraîner ({order_count} < {min_orders})."
        logger.info(reason)
        return RetrainResult(promoted=False, reason=reason, order_count=order_count)

    pipeline, metrics, run_id = train_and_track(*split_orders(pd.DataFrame(orders)))

    roc_auc = metrics["roc_auc"]
    if roc_auc < min_roc_auc:
        reason = f"ROC-AUC insuffisant ({roc_auc:.4f} < {min_roc_auc:.4f}) : modèle non promu."
        logger.warning(reason)
        return RetrainResult(promoted=False, reason=reason, order_count=order_count,
                             metrics=metrics, run_id=run_id)

    save_artifacts(pipeline, build_model_card(metrics, run_id), artifacts_dir)
    reason = f"Modèle promu (ROC-AUC={roc_auc:.4f}, {order_count} commandes)."
    logger.info(reason)
    return RetrainResult(promoted=True, reason=reason, order_count=order_count,
                         metrics=metrics, run_id=run_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Orchestration du réentraînement ML.")
    parser.add_argument("--mongo-uri", default=os.getenv("MONGO_URI", "mongodb://localhost:27017"))
    parser.add_argument("--db", default=os.getenv("MONGO_DB", "livraison_express"))
    parser.add_argument("--collection", default=os.getenv("MONGO_COLLECTION", "orders"))
    parser.add_argument("--min-orders", type=int, default=DEFAULT_MIN_ORDERS)
    parser.add_argument("--min-roc-auc", type=float, default=DEFAULT_MIN_ROC_AUC)
    parser.add_argument("--artifacts-dir", type=Path, default=ARTIFACTS_DIR)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    repo = build_order_repository(
        mongo_uri=args.mongo_uri,
        db_name=args.db,
        collection_name=args.collection,
    )
    try:
        result = run_retrain_pipeline(
            repository=repo,
            artifacts_dir=args.artifacts_dir,
            min_orders=args.min_orders,
            min_roc_auc=args.min_roc_auc,
        )
    finally:
        repo.close()
    print(result.reason)


if __name__ == "__main__":
    main()

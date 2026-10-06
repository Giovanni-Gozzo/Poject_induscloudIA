"""Chargement du modèle et calcul des prédictions."""
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
import sklearn

from app.schemas import OrderFeatures, Prediction

logger = logging.getLogger(__name__)


class ModelService:
    """Garde le modèle en mémoire et l'utilise pour prédire."""

    def __init__(self, model_path: Path, card_path: Path) -> None:
        self.model_path = model_path
        self.card_path = card_path
        self.model = None   # rien n'est chargé tant que load() n'a pas été appelé
        self.card = {}

    @property
    def is_loaded(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        card = json.loads(self.card_path.read_text(encoding="utf-8"))

        # Garde-fou n°1 : les features du modèle doivent être celles du contrat
        contrat = set(OrderFeatures.model_fields) - {"order_id"}
        modele = set(card["features"])
        if modele != contrat:
            raise RuntimeError(f"Features différentes entre modèle et contrat : {modele ^ contrat}")

        # Garde-fou n°2 : même version de scikit-learn qu'à l'entraînement
        if card.get("sklearn_version") != sklearn.__version__:
            logger.warning(
                "Modèle entraîné avec scikit-learn %s, mais l'API tourne avec %s",
                card.get("sklearn_version"), sklearn.__version__,
            )

        self.model = joblib.load(self.model_path)
        self.card = card
        logger.info("Modèle %s chargé", card["model_version"])

    def predict(self, order: OrderFeatures) -> Prediction:
        start = time.perf_counter()

        features = self.card["features"]
        # mode="json" : les Enum (Weather.normal...) redeviennent du texte ("normal"),
        # exactement comme dans les données d'entraînement
        ligne = order.model_dump(mode="json", include=set(features))
        X = pd.DataFrame([ligne])[features]  # même ordre de colonnes qu'à l'entraînement

        probability = float(self.model.predict_proba(X)[0, 1])
        eligible = probability >= self.card["threshold"]

        return Prediction(
            order_id=order.order_id,
            express_eligible=eligible,
            decision="oui" if eligible else "non",
            probability=round(probability, 4),
            model_version=self.card["model_version"],
            predicted_at=datetime.now(timezone.utc),
            latency_ms=round((time.perf_counter() - start) * 1000, 3),
        )
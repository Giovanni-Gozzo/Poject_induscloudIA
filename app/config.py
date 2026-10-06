"""Configuration de l'application.

Les chemins peuvent être changés par variable d'environnement, sans modifier le code.
C'est ce qui permettra d'avoir des réglages différents en dev, en test et en prod.
"""
import os
from pathlib import Path

SERVICE_NAME = "eligibilite-livraison-express"
APP_VERSION = "1.0.0"

ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "artifacts"))
MODEL_PATH = ARTIFACTS_DIR / "express_delivery_model.joblib"
MODEL_CARD_PATH = ARTIFACTS_DIR / "model_card.json"

# Connexion PostgreSQL (ADR-0001) : absente en dev et en test → stockage en mémoire
DATABASE_URL = os.getenv("DATABASE_URL")
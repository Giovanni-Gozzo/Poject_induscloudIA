"""Configuration de l'application.

Les chemins peuvent être changés par variable d'environnement, sans modifier le code.
C'est ce qui permettra d'avoir des réglages différents en dev, en test et en prod.
"""
import os
from pathlib import Path

SERVICE_NAME = "eligibilite-livraison-express"
APP_VERSION = "1.1.0"

ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "artifacts"))
MODEL_PATH = ARTIFACTS_DIR / "express_delivery_model.joblib"
MODEL_CARD_PATH = ARTIFACTS_DIR / "model_card.json"

# Connexion PostgreSQL (ADR-0001) : absente en dev et en test → stockage en mémoire
DATABASE_URL = os.getenv("DATABASE_URL")

# Sécurité (ADR-0006 et ADR-0007)
# Empreintes des clés d'API autorisées (JSON). Vide → toutes les routes /v1 renvoient 401.
API_KEYS = os.getenv("API_KEYS", "[]")
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
# /docs et /openapi.json exposent la structure de l'API : coupés par défaut (prod)
DOCS_ENABLED = os.getenv("DOCS_ENABLED", "false").lower() == "true"
"""Accès aux artefacts du modèle (ADR-0002).

L'API ne sait pas OÙ est rangé le modèle : elle passe par l'abstraction ModelRepository.
Aujourd'hui les fichiers sont dans l'image Docker (FileModelRepository) ; le jour où l'on
passe à un Model Registry MLflow, on ajoute une classe sans toucher à ModelService.
"""
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import joblib


class ModelRepository(ABC):
    """Les RÈGLES : ce que tout dépôt de modèle doit savoir fournir."""

    @abstractmethod
    def load_card(self) -> dict[str, Any]:
        """La model card : version, features, seuil, métriques, version de scikit-learn."""

    @abstractmethod
    def load_pipeline(self) -> Any:
        """La pipeline scikit-learn entraînée."""


class FileModelRepository(ModelRepository):
    """Les artefacts sont des fichiers locaux (copiés dans l'image Docker au build)."""

    def __init__(self, model_path: Path, card_path: Path) -> None:
        self.model_path = model_path
        self.card_path = card_path

    def load_card(self) -> dict[str, Any]:
        return json.loads(self.card_path.read_text(encoding="utf-8"))

    def load_pipeline(self) -> Any:
        # joblib exécute du code à la lecture : on ne charge QUE des fichiers produits
        # par notre propre build (jamais un fichier venant d'un utilisateur)
        return joblib.load(self.model_path)

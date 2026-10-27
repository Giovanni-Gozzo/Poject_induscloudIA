"""Tests de ModelService avec un faux dépôt de modèle (ADR-0002).

Grâce à l'abstraction ModelRepository, on teste les garde-fous sans aucun fichier.
"""
import pytest

from app.model import ModelService
from app.model_repository import ModelRepository
from app.schemas import OrderFeatures

FEATURES = [name for name in OrderFeatures.model_fields if name != "order_id"]


class FakeRepository(ModelRepository):
    def __init__(self, card: dict) -> None:
        self.card = card
        self.pipeline_loaded = False

    def load_card(self) -> dict:
        return self.card

    def load_pipeline(self) -> object:
        self.pipeline_loaded = True
        return object()


def card(**changes) -> dict:
    return {"model_version": "test", "features": FEATURES, "threshold": 0.5,
            "sklearn_version": "0.0.0", **changes}


def test_modele_charge_si_les_features_correspondent_au_contrat():
    service = ModelService(FakeRepository(card()))
    service.load()
    assert service.is_loaded
    assert service.card["model_version"] == "test"


def test_features_differentes_du_contrat_refusees_avant_de_charger_la_pipeline():
    repository = FakeRepository(card(features=FEATURES[:-1]))
    service = ModelService(repository)
    with pytest.raises(RuntimeError, match="Features différentes"):
        service.load()
    assert not service.is_loaded
    assert not repository.pipeline_loaded  # le fichier joblib n'a même pas été ouvert


def test_version_sklearn_differente_donne_un_avertissement(caplog):
    ModelService(FakeRepository(card(sklearn_version="0.0.0"))).load()
    assert "scikit-learn 0.0.0" in caplog.text

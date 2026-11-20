"""Tests de OrderRepository, de l'entraînement sur repository et de l'orchestration (TP4)."""
from unittest.mock import MagicMock

import mlflow
import pytest

from orchestration.retrain_pipeline import run_retrain_pipeline
from training.data import generate_orders_dataset
from training.repository import (
    InMemoryOrderRepository,
    MongoOrderRepository,
    build_order_repository,
)
from training.train import load_training_data


@pytest.fixture(autouse=True)
def isolated_mlflow(tmp_path, monkeypatch):
    """Les runs MLflow des tests vont dans un dossier temporaire, pas dans mlruns/ du projet."""
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path / 'mlflow.db'}")
    mlflow.set_tracking_uri(f"sqlite:///{tmp_path / 'mlflow.db'}")
    yield
    mlflow.set_tracking_uri(None)


class _FakeCollection:
    """Simulation minimale d'une collection PyMongo pour les tests unitaires."""

    def __init__(self) -> None:
        self._docs: dict[str, dict] = {}

    def replace_one(self, query: dict, doc: dict, upsert: bool = False) -> None:
        order_id = query["order_id"]
        if upsert or order_id in self._docs:
            stored = dict(doc)
            stored["_id"] = f"mongo-{order_id}"
            self._docs[order_id] = stored

    def find_one(self, query: dict, projection: dict | None = None) -> dict | None:
        doc = self._docs.get(query["order_id"])
        if doc is None:
            return None
        return _apply_projection(doc, projection)

    def find(self, _query: dict, projection: dict | None = None) -> list[dict]:
        return [_apply_projection(doc, projection) for doc in self._docs.values()]


def _apply_projection(doc: dict, projection: dict | None) -> dict:
    copy = dict(doc)
    if projection and projection.get("_id") == 0:
        copy.pop("_id", None)
    return copy


def _sample_orders(n_rows: int = 250) -> list[dict]:
    df = generate_orders_dataset(n_rows=n_rows)
    df["order_date"] = df["order_date"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return df.to_dict(orient="records")


# ============================ OrderRepository ============================
def test_in_memory_repository_crud():
    repo = InMemoryOrderRepository()
    order = {"order_id": "CMD-001", "distance_km": 3.5}
    repo.save(order)

    assert repo.get("CMD-001") == order
    assert repo.get("INCONNU") is None
    assert repo.get_all() == [order]


def test_in_memory_repository_requires_order_id():
    repo = InMemoryOrderRepository()
    with pytest.raises(ValueError, match="order_id"):
        repo.save({"distance_km": 2.0})


def test_mongo_repository_crud_without_internal_id():
    fake_collection = _FakeCollection()
    fake_client = {"livraison_express": {"orders": fake_collection}}
    repo = MongoOrderRepository(client=fake_client)

    order = {"order_id": "CMD-002", "distance_km": 4.2}
    repo.save(order)
    fetched = repo.get("CMD-002")

    assert fetched == order
    assert "_id" not in fetched
    assert repo.get("INCONNU") is None
    assert repo.get_all() == [order]


def test_build_order_repository_selects_backend():
    assert isinstance(build_order_repository(None), InMemoryOrderRepository)
    assert isinstance(build_order_repository("mongodb://localhost:27017"), MongoOrderRepository)


# ============================ Entraînement sur repo ============================
def test_load_training_data_from_repository_cleans_dirty_rows():
    records = _sample_orders(250)
    # Ajoute un doublon et une ligne invalide (distance négative) : doivent être nettoyés
    records.append(dict(records[0]))
    dirty = dict(records[1])
    dirty["order_id"] = "CMD-DIRTY"
    dirty["distance_km"] = -10.0
    records.append(dirty)

    repo = InMemoryOrderRepository(records)
    X_train, X_test, y_train, y_test = load_training_data(repository=repo)

    assert len(X_train) + len(X_test) == 250
    assert len(y_train) + len(y_test) == 250


def test_load_training_data_raises_when_repository_empty():
    repo = InMemoryOrderRepository()
    with pytest.raises(ValueError, match="Aucune commande"):
        load_training_data(repository=repo)


# ============================ Orchestrateur ============================
def test_retrain_pipeline_skips_when_not_enough_orders(tmp_path):
    repo = InMemoryOrderRepository(_sample_orders(50))
    result = run_retrain_pipeline(repo, artifacts_dir=tmp_path, min_orders=200)

    assert result.promoted is False
    assert "insuffisant" in result.reason
    assert not (tmp_path / "express_delivery_model.joblib").exists()


def test_retrain_pipeline_promotes_when_quality_is_good(tmp_path):
    repo = InMemoryOrderRepository(_sample_orders(250))
    result = run_retrain_pipeline(repo, artifacts_dir=tmp_path, min_orders=200, min_roc_auc=0.70)

    assert result.promoted is True
    assert result.metrics is not None
    assert result.metrics["roc_auc"] >= 0.70
    assert (tmp_path / "express_delivery_model.joblib").exists()
    assert (tmp_path / "model_card.json").exists()


def test_retrain_pipeline_rejects_low_quality_model(tmp_path, monkeypatch):
    repo = InMemoryOrderRepository(_sample_orders(250))
    fake_train = MagicMock(return_value=(MagicMock(), {"roc_auc": 0.45}, "run-123"))
    monkeypatch.setattr("orchestration.retrain_pipeline.train_and_track", fake_train)

    result = run_retrain_pipeline(repo, artifacts_dir=tmp_path, min_orders=200, min_roc_auc=0.70)

    assert result.promoted is False
    assert "non promu" in result.reason
    assert not (tmp_path / "express_delivery_model.joblib").exists()

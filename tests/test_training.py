"""Tests de l'entraînement (training/) : données, contrôles qualité, pipeline, model card.

Reprend les « simulations de données incorrectes » et les tests fonctionnels du notebook
(cellules 16 et 39), sur un petit jeu de données pour rester rapide.
"""
import pandas as pd
import pytest

from app.model import ModelService
from app.model_repository import FileModelRepository
from training.data import clean_orders_data, generate_orders_dataset, validate_dataset
from training.train import (FEATURE_COLUMNS, MODEL_CARD_FILENAME, MODEL_FILENAME,
                            build_model_card, build_pipeline, evaluate, load_training_data,
                            save_artifacts)

N_ROWS = 400


@pytest.fixture(scope="module")
def orders() -> pd.DataFrame:
    return generate_orders_dataset(n_rows=N_ROWS)


# ================================ données ================================
def test_generation_reproductible(orders):
    pd.testing.assert_frame_equal(orders, generate_orders_dataset(n_rows=N_ROWS))


def test_donnees_generees_passent_les_controles(orders):
    assert validate_dataset(orders) is True


@pytest.mark.parametrize("nom, abimer, message", [
    ("doublon", lambda df: pd.concat([df, df.iloc[[0]]]), "dupliqués"),
    ("colonne absente", lambda df: df.drop(columns="weather"), "absentes"),
    ("distance négative", lambda df: df.assign(distance_km=-1.0), "distance"),
    ("capacité > 1", lambda df: df.assign(carrier_capacity=1.5), "capacité"),
])
def test_controles_qualite_detectent_les_erreurs(orders, nom, abimer, message):
    with pytest.raises(ValueError, match=message):
        validate_dataset(abimer(orders))


def test_nettoyage_retire_doublons_et_valeurs_impossibles(orders):
    sale = pd.concat([orders, orders.iloc[[0]]], ignore_index=True)
    sale.loc[1, "distance_km"] = -5
    sale.loc[2, "weight_kg"] = None

    propre = clean_orders_data(sale)

    assert len(propre) == N_ROWS - 2
    assert validate_dataset(propre) is True
    assert len(sale) == N_ROWS + 1  # les données d'origine ne sont pas modifiées


# ============================ modèle ============================
@pytest.fixture(scope="module")
def trained():
    X_train, X_test, y_train, y_test = load_training_data(n_rows=N_ROWS)
    return build_pipeline().fit(X_train, y_train), X_test, y_test


def test_metriques_entre_0_et_1(trained):
    pipeline, X_test, y_test = trained
    metrics = evaluate(pipeline, X_test, y_test)
    assert set(metrics) == {"accuracy", "precision", "recall", "f1_score", "roc_auc"}
    assert all(0 <= value <= 1 for value in metrics.values())


def test_modele_meilleur_que_le_hasard(trained):
    pipeline, X_test, y_test = trained
    assert evaluate(pipeline, X_test, y_test)["roc_auc"] > 0.7


def test_model_card_contient_ce_que_l_api_attend():
    card = build_model_card({"accuracy": 0.81234567}, run_id=None)
    assert card["features"] == FEATURE_COLUMNS
    assert card["metrics"] == {"accuracy": 0.8123}
    assert {"model_version", "threshold", "sklearn_version", "trained_at"} <= set(card)


def test_artefacts_ecrits_puis_relus_par_l_api(trained, tmp_path):
    pipeline, _, _ = trained
    save_artifacts(pipeline, build_model_card({"accuracy": 0.8}, run_id=None), tmp_path)

    service = ModelService(FileModelRepository(tmp_path / MODEL_FILENAME,
                                               tmp_path / MODEL_CARD_FILENAME))
    service.load()
    assert service.is_loaded

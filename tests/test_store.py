"""Tests du stockage des commandes (ADR-0001).

Les tests PostgreSQL ne tournent que si une base de test est fournie :
    TEST_DATABASE_URL=postgresql://user:motdepasse@localhost:5432/db python -m pytest -v
⚠️ Ils vident les tables orders et predictions : ne jamais pointer vers la production.
"""
import os
from datetime import datetime, timezone

import pytest

from app.schemas import OrderFeatures, Prediction
from app.store import InMemoryOrderStore, PostgresOrderStore, build_store

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

COMMANDE = OrderFeatures(
    order_id="CMD-STORE-1",
    hour=14, day_of_week=2, weekend=0, distance_km=3.5, order_value_eur=89.9,
    weight_kg=2.4, stock_available=1, preparation_time_min=18.0, carrier_capacity=0.85,
    weather="normal", delivery_zone="centre", customer_type="premium",
)

PREDICTION = Prediction(
    order_id="CMD-STORE-1", express_eligible=True, decision="oui", probability=0.9377,
    model_version="1.0.0", predicted_at=datetime(2026, 10, 6, 14, 0, tzinfo=timezone.utc),
    latency_ms=12.5,
)


# ============================ choix du store ============================
def test_sans_database_url_on_reste_en_memoire():
    assert isinstance(build_store(None), InMemoryOrderStore)
    assert isinstance(build_store(""), InMemoryOrderStore)


def test_avec_database_url_on_passe_a_postgres():
    store = build_store("postgresql://u:p@localhost:1/db")
    assert isinstance(store, PostgresOrderStore)


def test_postgres_injoignable_ping_renvoie_false():
    # Port 1 : rien n'écoute, la connexion échoue → ping ne doit PAS lever d'exception
    store = PostgresOrderStore("postgresql://u:p@127.0.0.1:1/db?connect_timeout=1")
    assert store.ping() is False


# ============================== PostgreSQL ==============================
@pytest.fixture
def pg_store():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL non défini")
    store = PostgresOrderStore(TEST_DATABASE_URL)
    store.setup()
    with store._pool.connection() as conn:
        conn.execute("TRUNCATE orders, predictions")
    yield store
    store.close()


def test_postgres_commande_enregistree_puis_relue(pg_store):
    pg_store.save_order(COMMANDE)
    assert pg_store.get_order("CMD-STORE-1") == COMMANDE


def test_postgres_commande_inconnue_renvoie_none(pg_store):
    assert pg_store.get_order("CMD-INCONNUE") is None
    assert pg_store.get_prediction("CMD-INCONNUE") is None


def test_postgres_prediction_enregistree_puis_relue(pg_store):
    pg_store.save_prediction(PREDICTION)
    assert pg_store.get_prediction("CMD-STORE-1") == PREDICTION


def test_postgres_reenregistrer_remplace_comme_en_memoire(pg_store):
    pg_store.save_prediction(PREDICTION)
    pg_store.save_prediction(PREDICTION.model_copy(update={"decision": "non",
                                                           "express_eligible": False}))
    assert pg_store.get_prediction("CMD-STORE-1").decision == "non"


def test_postgres_donnees_conservees_apres_redemarrage(pg_store):
    pg_store.save_order(COMMANDE)
    pg_store.close()
    # Un nouveau store = l'API qui redémarre
    redemarre = PostgresOrderStore(TEST_DATABASE_URL)
    redemarre.setup()
    try:
        assert redemarre.get_order("CMD-STORE-1") == COMMANDE
    finally:
        redemarre.close()


def test_postgres_ping_ok(pg_store):
    assert pg_store.ping() is True

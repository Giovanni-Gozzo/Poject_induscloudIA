"""Tests automatiques de l'API (séance 1).

Lancement, depuis la racine du projet :
    python -m pytest -v
"""
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import app, model_service, store

# La commande « example_order » du notebook (cellule 20)
COMMANDE = {
    "hour": 14, "day_of_week": 2, "weekend": 0, "distance_km": 3.5,
    "order_value_eur": 89.9, "weight_kg": 2.4, "stock_available": 1,
    "preparation_time_min": 18, "carrier_capacity": 0.85,
    "weather": "normal", "delivery_zone": "centre", "customer_type": "premium",
}


@pytest.fixture(scope="module")
def client(admin_headers):
    """Un client de test authentifié (clé admin), avec le modèle chargé
    (le `with` déclenche le lifespan)."""
    with TestClient(app, headers=admin_headers) as c:
        yield c


@pytest.fixture(scope="module")
def anonymous_client():
    """Un client de test SANS clé d'API."""
    with TestClient(app) as c:
        yield c


# =============================== health ===============================
def test_health_repond_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready_quand_tout_va_bien(client):
    r = client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["checks"] == {"model": "loaded", "order_store": "reachable"}


def test_ready_503_sans_modele(client, monkeypatch):
    # monkeypatch remplace temporairement le modèle par None (restauré après le test)
    monkeypatch.setattr(model_service, "model", None)
    r = client.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "not_ready"


# ============================ predictions ============================
def test_prediction_valide(client):
    r = client.post("/v1/predictions", json=COMMANDE)
    assert r.status_code == 200
    resultat = r.json()
    assert 0 <= resultat["probability"] <= 1
    assert resultat["decision"] == ("oui" if resultat["express_eligible"] else "non")
    assert resultat["order_id"].startswith("CMD-")


def test_prediction_coherente_avec_le_notebook(client):
    r = client.post("/v1/predictions", json=COMMANDE)
    # Le notebook donnait 0.9366 ; on tolère un petit écart (modèle réentraîné)
    assert r.json()["probability"] == pytest.approx(0.9366, abs=0.02)


@pytest.mark.parametrize("nom, modification", [
    ("distance manquante", lambda c: c.pop("distance_km")),
    ("champ en trop",      lambda c: c.update(couleur="rouge")),
    ("météo inconnue",     lambda c: c.update(weather="grêle")),
    ("heure = 24",         lambda c: c.update(hour=24)),
    ("heure en texte",     lambda c: c.update(hour="14")),
    ("weekend en texte",   lambda c: c.update(weekend="1")),
    ("capacité = 1.5",     lambda c: c.update(carrier_capacity=1.5)),
])
def test_prediction_invalide_renvoie_422(client, nom, modification):
    commande = dict(COMMANDE)  # copie, pour ne pas abîmer COMMANDE
    modification(commande)
    r = client.post("/v1/predictions", json=commande)
    assert r.status_code == 422, nom
    assert r.json()["error"] == "validation_error"


def test_prediction_503_sans_modele(client, monkeypatch):
    monkeypatch.setattr(model_service, "model", None)
    r = client.post("/v1/predictions", json=COMMANDE)
    assert r.status_code == 503
    assert r.json()["error"] == "model_unavailable"


# =============================== orders ===============================
def test_commande_acceptee_puis_relue(client):
    r = client.post("/v1/orders", json={**COMMANDE, "order_id": "CMD-PYTEST-1"})
    assert r.status_code == 202
    assert r.json() == {"order_id": "CMD-PYTEST-1", "status": "accepted"}

    r = client.get("/v1/orders/CMD-PYTEST-1")
    assert r.status_code == 200
    assert r.json()["distance_km"] == 3.5


def test_commande_predite_en_arriere_plan(client):
    client.post("/v1/orders", json={**COMMANDE, "order_id": "CMD-PYTEST-2"})
    prediction = store.get_prediction("CMD-PYTEST-2")
    assert prediction is not None
    assert prediction.decision == "oui"


def test_commande_sans_id_recoit_un_id(client):
    r = client.post("/v1/orders", json=COMMANDE)
    assert r.status_code == 202
    assert r.json()["order_id"].startswith("CMD-")


def test_commande_inconnue_404(client):
    r = client.get("/v1/orders/CMD-INCONNUE")
    assert r.status_code == 404
    assert r.json()["error"] == "order_not_found"


def test_route_inexistante_404(client):
    r = client.get("/inexistant")
    assert r.status_code == 404
    assert r.json()["error"] == "not_found"


# ============================== sécurité ==============================
def test_health_reste_public(anonymous_client):
    assert anonymous_client.get("/health").status_code == 200
    assert anonymous_client.get("/health/ready").status_code == 200


@pytest.mark.parametrize("methode, chemin", [
    ("post", "/v1/predictions"),
    ("post", "/v1/orders"),
    ("get", "/v1/orders/CMD-PYTEST-1"),
])
def test_route_protegee_sans_cle_renvoie_401(anonymous_client, methode, chemin):
    r = anonymous_client.request(methode, chemin, json=COMMANDE)
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"


def test_cle_inconnue_renvoie_401(anonymous_client):
    r = anonymous_client.post("/v1/predictions", json=COMMANDE,
                              headers={"X-API-Key": "sk_cle_inventee"})
    assert r.status_code == 401
    assert r.json()["message"] == "Clé d'API invalide"


def test_cle_expiree_renvoie_401(anonymous_client, expired_headers):
    r = anonymous_client.post("/v1/predictions", json=COMMANDE, headers=expired_headers)
    assert r.status_code == 401
    assert r.json()["message"] == "Clé d'API expirée"


def test_sans_cle_une_commande_invalide_renvoie_401_pas_422(anonymous_client):
    # On ne révèle rien du format attendu à un client non authentifié
    r = anonymous_client.post("/v1/predictions", json={"pirate": True})
    assert r.status_code == 401


def test_role_user_peut_predire(anonymous_client, user_headers):
    r = anonymous_client.post("/v1/predictions", json=COMMANDE, headers=user_headers)
    assert r.status_code == 200


def test_role_user_ne_peut_pas_relire_une_commande(anonymous_client, user_headers):
    anonymous_client.post("/v1/orders", json={**COMMANDE, "order_id": "CMD-PYTEST-3"},
                          headers=user_headers)
    r = anonymous_client.get("/v1/orders/CMD-PYTEST-3", headers=user_headers)
    assert r.status_code == 403
    assert r.json()["error"] == "forbidden"


def test_entetes_de_securite_presents(client):
    r = client.post("/v1/predictions", json=COMMANDE)
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Cache-Control"] == "no-store"


def test_documentation_desactivee_par_defaut(anonymous_client):
    assert anonymous_client.get("/docs").status_code == 404
    assert anonymous_client.get("/openapi.json").status_code == 404


# ============================ contrat OpenAPI ============================
SEANCE_COURANTE = 2


def test_conformite_au_contrat():
    """Chaque opération attendue jusqu'à la séance courante existe,
    avec le bon operationId et au moins les codes de réponse du contrat."""
    attendu = yaml.safe_load(Path("openapi.yml").read_text(encoding="utf-8"))
    genere = app.openapi()  # le contrat que FastAPI génère à partir de ton code

    for chemin, operations in attendu["paths"].items():
        for methode, operation in operations.items():
            if operation.get("x-session", 99) > SEANCE_COURANTE:
                continue  # pas encore attendue
            assert chemin in genere["paths"], f"Route manquante : {chemin}"
            assert methode in genere["paths"][chemin], \
                f"Méthode manquante : {methode.upper()} {chemin}"

            operation_generee = genere["paths"][chemin][methode]
            assert operation_generee["operationId"] == operation["operationId"]

            manquants = set(operation["responses"]) - set(operation_generee["responses"])
            assert not manquants, f"{operation['operationId']} : codes manquants {manquants}"
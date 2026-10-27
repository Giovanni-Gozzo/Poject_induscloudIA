"""Tests unitaires de la sécurité (ADR-0007) : clés, rôles, expiration, limitation de débit."""
import json
from datetime import date

import pytest

from app.errors import ApiError
from app.security import (ApiKey, ApiKeyRegistry, Authenticator, RateLimiter, Role,
                          generate_key, hash_key, parse_api_keys)

CLE = "sk_cle_de_test"
ENTREE = {"name": "boutique", "role": "user", "sha256": hash_key(CLE), "expires_at": "2026-12-31"}


class FakeClock:
    """Horloge que le test fait avancer à la main."""

    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


# ============================ lecture de API_KEYS ============================
def test_parse_api_keys_lit_une_entree_valide():
    [key] = parse_api_keys(json.dumps([ENTREE]))
    assert key == ApiKey(name="boutique", role=Role.user, sha256=hash_key(CLE),
                         expires_at=date(2026, 12, 31))


def test_parse_api_keys_vide_ou_absent_donne_aucune_cle():
    assert parse_api_keys(None) == []
    assert parse_api_keys("[]") == []


@pytest.mark.parametrize("contenu", [
    "pas du json",
    json.dumps([{**ENTREE, "role": "superadmin"}]),     # rôle inconnu
    json.dumps([{**ENTREE, "expires_at": "bientôt"}]),  # date invalide
    json.dumps([{"name": "sans-empreinte", "role": "user", "expires_at": "2026-12-31"}]),
    json.dumps({"pas": "une liste"}),
])
def test_parse_api_keys_invalide_leve_une_erreur(contenu):
    with pytest.raises(ValueError, match="API_KEYS invalide"):
        parse_api_keys(contenu)


def test_generate_key_produit_des_cles_uniques_et_prefixees():
    cles = {generate_key() for _ in range(100)}
    assert len(cles) == 100
    assert all(cle.startswith("sk_") for cle in cles)


# ============================ authentification ============================
def registre(today: date = date(2026, 10, 27)) -> ApiKeyRegistry:
    return ApiKeyRegistry(parse_api_keys(json.dumps([ENTREE])), today=lambda: today)


def test_bonne_cle_est_reconnue():
    assert registre().authenticate(CLE).name == "boutique"


@pytest.mark.parametrize("cle", [None, "", "sk_mauvaise"])
def test_cle_absente_ou_fausse_renvoie_401(cle):
    with pytest.raises(ApiError) as exc:
        registre().authenticate(cle)
    assert exc.value.status_code == 401


def test_cle_valide_le_dernier_jour_puis_expiree_le_lendemain():
    assert registre(today=date(2026, 12, 31)).authenticate(CLE)
    with pytest.raises(ApiError) as exc:
        registre(today=date(2027, 1, 1)).authenticate(CLE)
    assert exc.value.message == "Clé d'API expirée"


# ================================ rôles ================================
def test_admin_a_les_droits_user_mais_pas_l_inverse():
    admin = ApiKey("a", Role.admin, "x", date(2999, 1, 1))
    user = ApiKey("u", Role.user, "y", date(2999, 1, 1))
    assert admin.allows(Role.user) and admin.allows(Role.admin)
    assert user.allows(Role.user) and not user.allows(Role.admin)


# ========================== limitation de débit ==========================
def test_rate_limiter_bloque_au_dela_de_la_limite_puis_repart():
    horloge = FakeClock(now=10)
    limiter = RateLimiter(limit_per_minute=3, clock=horloge)

    assert [limiter.allow("boutique") for _ in range(4)] == [True, True, True, False]
    assert limiter.allow("autre-client")  # chaque client a son propre compteur

    horloge.now = 61  # minute suivante
    assert limiter.allow("boutique")


def test_rate_limiter_indique_quand_reessayer():
    limiter = RateLimiter(limit_per_minute=1, clock=FakeClock(now=50))
    assert limiter.seconds_until_reset() == 11


def test_authenticator_renvoie_429_avec_retry_after():
    auth = Authenticator(registre(), RateLimiter(limit_per_minute=1, clock=FakeClock()))
    dependance = auth.require(Role.user)
    dependance(CLE)
    with pytest.raises(ApiError) as exc:
        dependance(CLE)
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "61"


def test_authenticator_renvoie_403_si_role_insuffisant():
    auth = Authenticator(registre(), RateLimiter(limit_per_minute=10))
    with pytest.raises(ApiError) as exc:
        auth.require(Role.admin)(CLE)
    assert exc.value.status_code == 403

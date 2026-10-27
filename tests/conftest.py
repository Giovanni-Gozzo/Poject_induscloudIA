"""Configuration commune des tests.

pytest lit ce fichier AVANT les modules de test : on y définit les clés d'API de test
avant que app.main ne lise la variable d'environnement API_KEYS.
Ces clés sont factices et n'existent que pendant les tests.
"""
import json
import os

import pytest

from app.security import hash_key

USER_KEY = "sk_test_user"
ADMIN_KEY = "sk_test_admin"
EXPIRED_KEY = "sk_test_expired"

os.environ["API_KEYS"] = json.dumps([
    {"name": "test-user", "role": "user", "sha256": hash_key(USER_KEY),
     "expires_at": "2999-12-31"},
    {"name": "test-admin", "role": "admin", "sha256": hash_key(ADMIN_KEY),
     "expires_at": "2999-12-31"},
    {"name": "test-expired", "role": "admin", "sha256": hash_key(EXPIRED_KEY),
     "expires_at": "2000-01-01"},
])
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"  # les tests d'API ne doivent pas être limités


@pytest.fixture(scope="session")
def user_headers() -> dict[str, str]:
    return {"X-API-Key": USER_KEY}


@pytest.fixture(scope="session")
def admin_headers() -> dict[str, str]:
    return {"X-API-Key": ADMIN_KEY}


@pytest.fixture(scope="session")
def expired_headers() -> dict[str, str]:
    return {"X-API-Key": EXPIRED_KEY}

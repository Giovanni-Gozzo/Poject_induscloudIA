"""Sécurisation de l'accès à l'API : clés d'API, rôles, expiration, limitation de débit (ADR-0007).

Les clés ne sont JAMAIS stockées en clair : la variable d'environnement API_KEYS ne contient
que leur empreinte SHA-256. Une fuite de cette variable ne permet donc pas d'appeler l'API.

Format de API_KEYS (JSON), généré par `python -m scripts.new_api_key` :
    [{"name": "boutique-web", "role": "user", "sha256": "…", "expires_at": "2027-01-25"}]
"""
import hashlib
import json
import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import Enum
from threading import Lock

from fastapi import Security
from fastapi.security import APIKeyHeader

from app.errors import ApiError

logger = logging.getLogger(__name__)

API_KEY_HEADER_NAME = "X-API-Key"
API_KEY_PREFIX = "sk_"
RATE_LIMIT_WINDOW_S = 60


class Role(str, Enum):
    user = "user"     # envoie des commandes et demande des prédictions
    admin = "admin"   # peut en plus relire les commandes collectées


# Ce que chaque rôle a le droit de faire : un admin peut tout ce que peut un user
GRANTED_ROLES = {
    Role.user: {Role.user},
    Role.admin: {Role.user, Role.admin},
}


@dataclass(frozen=True)
class ApiKey:
    name: str          # à qui appartient la clé, ex. « boutique-web »
    role: Role
    sha256: str        # empreinte de la clé, jamais la clé elle-même
    expires_at: date

    def is_expired(self, today: date) -> bool:
        return today > self.expires_at

    def allows(self, role: Role) -> bool:
        return role in GRANTED_ROLES[self.role]


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_key() -> str:
    """Nouvelle clé aléatoire, ex. sk_Xq3…  (256 bits d'aléa)."""
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def parse_api_keys(raw_json: str | None) -> list[ApiKey]:
    """Lit API_KEYS. Lève une ValueError si le contenu est invalide (on refuse de démarrer)."""
    try:
        entries = json.loads(raw_json or "[]")
        return [
            ApiKey(name=e["name"], role=Role(e["role"]), sha256=e["sha256"].lower(),
                   expires_at=date.fromisoformat(e["expires_at"]))
            for e in entries
        ]
    except (TypeError, KeyError, AttributeError, ValueError) as exc:
        raise ValueError(f"Variable API_KEYS invalide : {exc}") from exc


class ApiKeyRegistry:
    """Retrouve la clé correspondant à ce que le client envoie."""

    def __init__(self, keys: list[ApiKey], today: Callable[[], date] = date.today) -> None:
        self._keys = {key.sha256: key for key in keys}
        self._today = today
        if not self._keys:
            logger.warning("Aucune clé d'API configurée : toutes les routes protégées renverront 401")

    def authenticate(self, raw_key: str | None) -> ApiKey:
        if not raw_key:
            raise ApiError(401, "unauthorized", f"En-tête {API_KEY_HEADER_NAME} manquant")
        key = self._keys.get(hash_key(raw_key))
        if key is None:
            raise ApiError(401, "unauthorized", "Clé d'API invalide")
        if key.is_expired(self._today()):
            logger.warning("Clé d'API expirée utilisée : %s", key.name)
            raise ApiError(401, "unauthorized", "Clé d'API expirée")
        return key


class RateLimiter:
    """Limite le nombre d'appels par client et par minute (fenêtre fixe, en mémoire)."""

    def __init__(self, limit_per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._limit = limit_per_minute
        self._clock = clock
        self._windows: dict[str, tuple[int, int]] = {}  # client → (n° de fenêtre, nb d'appels)
        self._lock = Lock()

    def allow(self, client_id: str) -> bool:
        window = int(self._clock() // RATE_LIMIT_WINDOW_S)
        with self._lock:
            start, count = self._windows.get(client_id, (window, 0))
            if start != window:
                count = 0  # nouvelle minute : le compteur repart de zéro
            if count >= self._limit:
                return False
            self._windows = {**self._windows, client_id: (window, count + 1)}
            return True

    def seconds_until_reset(self) -> int:
        return int(RATE_LIMIT_WINDOW_S - self._clock() % RATE_LIMIT_WINDOW_S) + 1


api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False,
                              description="Clé d'API fournie par l'administrateur")


class Authenticator:
    """Fabrique les dépendances FastAPI qui protègent les routes."""

    def __init__(self, registry: ApiKeyRegistry, rate_limiter: RateLimiter) -> None:
        self._registry = registry
        self._rate_limiter = rate_limiter

    def require(self, role: Role) -> Callable[..., ApiKey]:
        def dependency(raw_key: str | None = Security(api_key_header)) -> ApiKey:
            key = self._registry.authenticate(raw_key)                # 401 : qui es-tu ?
            if not key.allows(role):                                  # 403 : as-tu le droit ?
                raise ApiError(403, "forbidden", f"Rôle « {role.value} » requis")
            if not self._rate_limiter.allow(key.name):                # 429 : pas trop vite !
                raise ApiError(429, "rate_limited", "Trop de requêtes, réessayez plus tard",
                               headers={"Retry-After": str(self._rate_limiter.seconds_until_reset())})
            return key
        return dependency

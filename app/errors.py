"""Transforme toutes les erreurs au format Error du contrat."""
import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas import Error

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Erreur métier que l'on lève volontairement dans nos routes."""

    def __init__(self, status_code: int, error: str, message: str,
                 details: list[str] | None = None) -> None:
        self.status_code = status_code
        self.error = error
        self.message = message
        self.details = details


def _reponse(status_code: int, erreur: Error) -> JSONResponse:
    # exclude_none : on n'affiche pas "details" s'il est vide
    return JSONResponse(status_code=status_code, content=erreur.model_dump(exclude_none=True))


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    """Nos erreurs volontaires : 404 commande inconnue, 503 modèle indisponible..."""
    return _reponse(exc.status_code, Error(error=exc.error, message=exc.message,
                                           details=exc.details))


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Les erreurs 422 produites par Pydantic."""
    details = []
    for e in exc.errors():
        # e["loc"] vaut par exemple ("body", "weekend") : on garde "weekend"
        champ = ".".join(str(partie) for partie in e["loc"][1:]) or "body"
        details.append(f"{champ} : {e['msg']}")
    return _reponse(422, Error(error="validation_error", message="Commande invalide",
                               details=details))


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Les erreurs HTTP standard, par exemple une route inexistante (404)."""
    codes = {404: "not_found", 405: "method_not_allowed"}
    return _reponse(exc.status_code, Error(error=codes.get(exc.status_code, "http_error"),
                                           message=str(exc.detail)))


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Filet de sécurité : tout bug imprévu devient une 500 propre."""
    logger.exception("Erreur non gérée")  # le détail va dans les logs, pas chez le client
    return _reponse(500, Error(error="internal_error", message="Erreur interne"))
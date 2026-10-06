# syntax=docker/dockerfile:1

# Même version de Python que le devcontainer
ARG PYTHON_VERSION=3.13

# ------------------------------------------------------------------
# Étape 1 : entraînement du modèle
# Produit artifacts/express_delivery_model.joblib et artifacts/model_card.json
# (artifacts/ est ignoré par git : le modèle est donc recréé à chaque build)
# ------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS train

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# requirements.lock.txt sert de contraintes : mêmes versions exactes partout
COPY requirements.txt requirements.lock.txt ./
RUN pip install -r requirements.txt mlflow skops -c requirements.lock.txt

COPY training/ training/
RUN python -m training.train


# ------------------------------------------------------------------
# Étape 2 : image finale de l'API (sans MLflow ni outils d'entraînement)
# ------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ARTIFACTS_DIR=/app/artifacts \
    PORT=8000

WORKDIR /app

COPY requirements.txt requirements.lock.txt ./
RUN pip install -r requirements.txt -c requirements.lock.txt

# L'API ne tourne pas en root
RUN useradd --create-home --uid 1000 appuser

COPY app/ app/
COPY --from=train /build/artifacts/express_delivery_model.joblib \
                  /build/artifacts/model_card.json \
                  artifacts/

USER appuser

EXPOSE 8000

# /health/ready répond 503 tant que le modèle n'est pas chargé
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health/ready', timeout=4)"

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]

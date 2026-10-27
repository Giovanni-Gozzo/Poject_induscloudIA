# syntax=docker/dockerfile:1

# Même version de Python que le devcontainer
ARG PYTHON_VERSION=3.13

# ------------------------------------------------------------------
# Étape 1 : dépendances de l'API, installées dans un environnement virtuel
# (seul ce dossier /opt/venv est copié dans l'image finale)
# ------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH=/opt/venv/bin:$PATH

# requirements.lock.txt sert de contraintes : mêmes versions exactes partout
COPY requirements.txt requirements.lock.txt /tmp/
RUN python -m venv /opt/venv \
 && pip install -r /tmp/requirements.txt -c /tmp/requirements.lock.txt


# ------------------------------------------------------------------
# Étape 2 : entraînement du modèle (MLflow n'est installé QUE ici)
# Produit artifacts/express_delivery_model.joblib et artifacts/model_card.json
# (artifacts/ est ignoré par git : le modèle est donc recréé à chaque build)
# ------------------------------------------------------------------
FROM deps AS train

WORKDIR /build
RUN pip install mlflow skops -c /tmp/requirements.lock.txt
COPY training/ training/
RUN python -m training.train


# ------------------------------------------------------------------
# Étape 3 : image finale de l'API
# Sans pip, sans MLflow, sans code d'entraînement ni tests
# ------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG VERSION=dev
LABEL org.opencontainers.image.title="eligibilite-livraison-express" \
      org.opencontainers.image.description="API de prédiction d'éligibilité à la livraison express" \
      org.opencontainers.image.source="https://github.com/Giovanni-Gozzo/Poject_induscloudIA" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    ARTIFACTS_DIR=/app/artifacts \
    PORT=8000

WORKDIR /app

# L'API ne tourne pas en root
RUN useradd --create-home --uid 1000 appuser

# Environnement virtuel de l'étape 1, puis suppression de pip (venv ET système) :
# un attaquant qui prendrait la main sur le conteneur ne pourrait rien installer
COPY --from=deps /opt/venv /opt/venv
RUN /opt/venv/bin/python -m pip uninstall -y pip \
 && /usr/local/bin/python -m pip uninstall -y pip

# Fichiers appartenant à root, en lecture seule pour appuser : le code ne peut pas être modifié
COPY app/ app/
COPY --from=train /build/artifacts/express_delivery_model.joblib \
                  /build/artifacts/model_card.json \
                  artifacts/

USER appuser

# Seul port exposé : celui de l'API (pas de SSH dans le conteneur)
EXPOSE 8000

# /health/ready répond 503 tant que le modèle n'est pas chargé
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health/ready', timeout=4)"

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]

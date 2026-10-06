-- Schéma de stockage des commandes et des prédictions (ADR-0001).
-- Idempotent : exécuté au démarrage de l'API, sans effet si les tables existent déjà.

-- Les features sont gardées en JSONB : le contrat (OrderFeatures) les valide déjà,
-- et ajouter une feature ne demande pas de migration de table.
CREATE TABLE IF NOT EXISTS orders (
    order_id   TEXT PRIMARY KEY,
    features   JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Pas de clé étrangère vers orders : POST /v1/predictions enregistre aussi
-- des prédictions pour des commandes qui n'ont pas été collectées.
CREATE TABLE IF NOT EXISTS predictions (
    order_id         TEXT PRIMARY KEY,
    express_eligible BOOLEAN NOT NULL,
    decision         TEXT NOT NULL,
    probability      DOUBLE PRECISION NOT NULL,
    model_version    TEXT NOT NULL,
    predicted_at     TIMESTAMPTZ NOT NULL,
    latency_ms       DOUBLE PRECISION
);

"""Entraînement reproductible du modèle d'éligibilité express.

Lancement, depuis la racine du projet :
    python -m training.train
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, f1_score, precision_score, recall_score, roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from training.data import clean_orders_data, generate_orders_dataset, validate_dataset

# ------------------------------------------------------------------
# Paramètres : regroupés en haut du fichier, pour les trouver et les changer facilement
# ------------------------------------------------------------------
PROJECT_NAME = "eligibilite-livraison-express"
MODEL_VERSION = "1.0.0"
RANDOM_STATE = 42
THRESHOLD = 0.5
TEST_SIZE = 0.20
ARTIFACTS_DIR = Path("artifacts")
MODEL_FILENAME = "express_delivery_model.joblib"
MODEL_CARD_FILENAME = "model_card.json"

TARGET = "express_eligible"
NUMERIC_FEATURES = [
    "hour", "day_of_week", "weekend", "distance_km", "order_value_eur",
    "weight_kg", "stock_available", "preparation_time_min", "carrier_capacity",
]
CATEGORICAL_FEATURES = ["weather", "delivery_zone", "customer_type"]
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES

LIMITATIONS = [
    "Le jeu de données utilisé est synthétique.",
    "La décision ne doit pas être utilisée sans validation des règles métier.",
    "Les performances peuvent varier sur des données réelles.",
    "Le modèle ne remplace pas une analyse des contraintes opérationnelles.",
]


def build_pipeline() -> Pipeline:
    """Construit la pipeline scikit-learn (cellule 24 du notebook)."""
    numeric = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])
    categorical = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    preprocessor = ColumnTransformer([
        ("numeric", numeric, NUMERIC_FEATURES),
        ("categorical", categorical, CATEGORICAL_FEATURES),
    ])
    classifier = LogisticRegression(
        max_iter=1000, class_weight="balanced", random_state=RANDOM_STATE
    )
    return Pipeline([("preprocessor", preprocessor), ("classifier", classifier)])


def load_training_data(n_rows: int = 6000):
    """Données propres et validées, découpées en entraînement / test (cellules 8 à 22)."""
    orders = clean_orders_data(generate_orders_dataset(n_rows=n_rows, random_state=RANDOM_STATE))
    validate_dataset(orders)
    X, y = orders[FEATURE_COLUMNS], orders[TARGET]
    return train_test_split(X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y)


def evaluate(pipeline: Pipeline, X_test: pd.DataFrame, y_test: pd.Series) -> dict[str, float]:
    """Métriques du modèle sur le jeu de test, au seuil THRESHOLD (cellule 26)."""
    proba = pipeline.predict_proba(X_test)[:, 1]
    pred = (proba >= THRESHOLD).astype(int)
    return {
        "accuracy": accuracy_score(y_test, pred),
        "precision": precision_score(y_test, pred, zero_division=0),
        "recall": recall_score(y_test, pred, zero_division=0),
        "f1_score": f1_score(y_test, pred, zero_division=0),
        "roc_auc": roc_auc_score(y_test, proba),
    }


def train_and_track(X_train, X_test, y_train, y_test) -> tuple[Pipeline, dict[str, float], str]:
    """Entraîne, évalue et enregistre le run dans MLflow. Renvoie (pipeline, métriques, run_id)."""
    pipeline = build_pipeline()
    mlflow.set_experiment("livraison-express")
    with mlflow.start_run(run_name="logistic-regression-baseline") as run:
        pipeline.fit(X_train, y_train)
        metrics = evaluate(pipeline, X_test, y_test)

        mlflow.log_params({
            "model_type": "LogisticRegression",
            "random_state": RANDOM_STATE,
            "threshold": THRESHOLD,
            "feature_count": len(FEATURE_COLUMNS),
        })
        mlflow.log_metrics(metrics)
        mlflow.sklearn.log_model(
            pipeline,
            name="model",                         # remplace artifact_path (déprécié)
            skops_trusted_types=["numpy.dtype"],  # corrige l'erreur de la cellule 14
            input_example=X_train.head(3),        # MLflow en déduit le format d'entrée
        )
        return pipeline, metrics, run.info.run_id


def build_model_card(metrics: dict[str, float], run_id: str | None) -> dict:
    """Model card lue par l'API au démarrage (cellule 55)."""
    return {
        "project": PROJECT_NAME,
        "model_version": MODEL_VERSION,
        "model_type": "Logistic regression",
        "task": "binary classification",
        "target": TARGET,
        "threshold": THRESHOLD,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "features": FEATURE_COLUMNS,
        "metrics": {name: round(float(value), 4) for name, value in metrics.items()},
        "limitations": LIMITATIONS,
        "sklearn_version": sklearn.__version__,
        "mlflow_run_id": run_id,
    }


def save_artifacts(pipeline: Pipeline, model_card: dict, artifacts_dir: Path) -> None:
    """Écrit les deux artefacts consommés par l'API (ADR-0002)."""
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, artifacts_dir / MODEL_FILENAME)
    (artifacts_dir / MODEL_CARD_FILENAME).write_text(
        json.dumps(model_card, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main() -> None:
    X_train, X_test, y_train, y_test = load_training_data()
    print(f"Entraînement : {len(X_train)} lignes | Test : {len(X_test)} lignes")

    pipeline, metrics, run_id = train_and_track(X_train, X_test, y_train, y_test)
    model_card = build_model_card(metrics, run_id)
    save_artifacts(pipeline, model_card, ARTIFACTS_DIR)

    print("Métriques :")
    for name, value in model_card["metrics"].items():
        print(f"  {name:>10} : {value}")
    print(f"Artefacts écrits dans : {ARTIFACTS_DIR.resolve()}")


if __name__ == "__main__":
    main()

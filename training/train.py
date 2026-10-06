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
ARTIFACTS_DIR = Path("artifacts")

TARGET = "express_eligible"
NUMERIC_FEATURES = [
    "hour", "day_of_week", "weekend", "distance_km", "order_value_eur",
    "weight_kg", "stock_available", "preparation_time_min", "carrier_capacity",
]
CATEGORICAL_FEATURES = ["weather", "delivery_zone", "customer_type"]
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def build_pipeline() -> Pipeline:
    """Construit la pipeline scikit-learn (cellule 13 du notebook)."""
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


def main() -> None:
    ARTIFACTS_DIR.mkdir(exist_ok=True)

    # 1. Données
    orders = clean_orders_data(generate_orders_dataset(random_state=RANDOM_STATE))
    validate_dataset(orders)
    X, y = orders[FEATURE_COLUMNS], orders[TARGET]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=RANDOM_STATE, stratify=y
    )
    print(f"Entraînement : {len(X_train)} lignes | Test : {len(X_test)} lignes")

    # 2. Entraînement + suivi MLflow
    pipeline = build_pipeline()
    mlflow.set_experiment("livraison-express")
    with mlflow.start_run(run_name="logistic-regression-baseline") as run:
        pipeline.fit(X_train, y_train)

        proba = pipeline.predict_proba(X_test)[:, 1]
        pred = (proba >= THRESHOLD).astype(int)
        metrics = {
            "accuracy": accuracy_score(y_test, pred),
            "precision": precision_score(y_test, pred, zero_division=0),
            "recall": recall_score(y_test, pred, zero_division=0),
            "f1_score": f1_score(y_test, pred, zero_division=0),
            "roc_auc": roc_auc_score(y_test, proba),
        }

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
        run_id = run.info.run_id

    # 3. Sauvegarde des artefacts consommés par l'API
    joblib.dump(pipeline, ARTIFACTS_DIR / "express_delivery_model.joblib")

    model_card = {
        "project": PROJECT_NAME,
        "model_version": MODEL_VERSION,
        "model_type": "Logistic regression",
        "task": "binary classification",
        "target": TARGET,
        "threshold": THRESHOLD,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "features": FEATURE_COLUMNS,
        "metrics": {name: round(float(value), 4) for name, value in metrics.items()},
        "limitations": [
            "Le jeu de données utilisé est synthétique.",
            "La décision ne doit pas être utilisée sans validation des règles métier.",
            "Les performances peuvent varier sur des données réelles.",
            "Le modèle ne remplace pas une analyse des contraintes opérationnelles.",
        ],
        "sklearn_version": sklearn.__version__,
        "mlflow_run_id": run_id,
    }
    (ARTIFACTS_DIR / "model_card.json").write_text(
        json.dumps(model_card, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("Métriques :")
    for name, value in model_card["metrics"].items():
        print(f"  {name:>10} : {value}")
    print(f"Artefacts écrits dans : {ARTIFACTS_DIR.resolve()}")


if __name__ == "__main__":
    main()
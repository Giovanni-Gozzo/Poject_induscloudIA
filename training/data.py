"""Génération, contrôle qualité et nettoyage des données de commandes.

Code extrait des cellules 4, 8 et 10 du notebook.
"""
import numpy as np
import pandas as pd


def generate_orders_dataset(n_rows=6000, random_state=42):
    """Génère un jeu de données fictif représentant des commandes."""
    rng = np.random.default_rng(random_state)

    order_date = pd.date_range(start="2025-01-01", end="2025-12-31", periods=n_rows)
    hour = rng.integers(7, 23, size=n_rows)
    day_of_week = pd.Series(order_date).dt.dayofweek.to_numpy()
    weekend = (day_of_week >= 5).astype(int)

    data = pd.DataFrame({
        "order_id": [f"CMD-{i:06d}" for i in range(1, n_rows + 1)],
        "order_date": order_date,
        "hour": hour,
        "day_of_week": day_of_week,
        "weekend": weekend,
        "distance_km": np.round(rng.gamma(shape=2.0, scale=4.0, size=n_rows), 2),
        "order_value_eur": np.round(rng.uniform(10, 250, size=n_rows), 2),
        "weight_kg": np.round(rng.uniform(0.2, 25, size=n_rows), 2),
        "stock_available": rng.binomial(1, 0.85, size=n_rows),
        "preparation_time_min": np.round(
            rng.normal(loc=25, scale=10, size=n_rows).clip(5, 90), 1
        ),
        "carrier_capacity": np.round(rng.uniform(0.2, 1.0, size=n_rows), 2),
        "weather": rng.choice(
            ["normal", "pluie", "neige", "orage"], size=n_rows, p=[0.65, 0.20, 0.10, 0.05]
        ),
        "delivery_zone": rng.choice(
            ["centre", "proche_banlieue", "banlieue", "rurale"],
            size=n_rows, p=[0.30, 0.30, 0.25, 0.15],
        ),
        "customer_type": rng.choice(["standard", "premium"], size=n_rows, p=[0.80, 0.20]),
    })

    zone_penalty = data["delivery_zone"].map(
        {"centre": 0, "proche_banlieue": 0.10, "banlieue": 0.25, "rurale": 0.45}
    )
    weather_penalty = data["weather"].map(
        {"normal": 0, "pluie": 0.10, "neige": 0.25, "orage": 0.30}
    )
    customer_bonus = (data["customer_type"] == "premium").astype(int) * 0.15

    # Score latent simulant une décision métier
    score = (
        2.5
        - 0.18 * data["distance_km"]
        - 0.035 * data["preparation_time_min"]
        - 0.035 * data["weight_kg"]
        - zone_penalty
        - weather_penalty
        + 1.8 * data["stock_available"]
        + 1.3 * data["carrier_capacity"]
        + customer_bonus
        - 0.40 * data["weekend"]
        - 0.08 * np.maximum(data["hour"] - 18, 0)
    )
    probability = 1 / (1 + np.exp(-score))
    data["express_eligible"] = rng.binomial(1, probability)
    return data


def validate_dataset(df):
    """Contrôles de qualité élémentaires. Lève une ValueError si un contrôle échoue."""
    required_columns = {
        "order_id", "order_date", "hour", "day_of_week", "weekend", "distance_km",
        "order_value_eur", "weight_kg", "stock_available", "preparation_time_min",
        "carrier_capacity", "weather", "delivery_zone", "customer_type", "express_eligible",
    }
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"Colonnes obligatoires absentes : {sorted(missing_columns)}")
    if df["order_id"].duplicated().any():
        raise ValueError("Des identifiants de commande sont dupliqués.")
    if df["express_eligible"].isna().any():
        raise ValueError("La variable cible contient des valeurs manquantes.")
    if not df["hour"].between(0, 23).all():
        raise ValueError("Certaines heures sont invalides.")
    if not df["distance_km"].ge(0).all():
        raise ValueError("La distance ne peut pas être négative.")
    if not df["weight_kg"].ge(0).all():
        raise ValueError("Le poids ne peut pas être négatif.")
    if not df["preparation_time_min"].ge(0).all():
        raise ValueError("Le temps de préparation ne peut pas être négatif.")
    if not df["carrier_capacity"].between(0, 1).all():
        raise ValueError("La capacité du transporteur doit être comprise entre 0 et 1.")
    if not df["stock_available"].isin([0, 1]).all():
        raise ValueError("La variable stock_available doit contenir uniquement 0 ou 1.")
    return True


def clean_orders_data(df):
    """Nettoyage automatique : doublons, dates, valeurs manquantes et bornes."""
    cleaned = df.copy()
    cleaned = cleaned.drop_duplicates(subset=["order_id"], keep="last")
    cleaned["order_date"] = pd.to_datetime(cleaned["order_date"], errors="coerce")

    essential_columns = [
        "order_id", "distance_km", "weight_kg", "stock_available",
        "preparation_time_min", "carrier_capacity", "express_eligible",
    ]
    cleaned = cleaned.dropna(subset=essential_columns)

    cleaned = cleaned[cleaned["distance_km"] >= 0]
    cleaned = cleaned[cleaned["weight_kg"] >= 0]
    cleaned = cleaned[cleaned["preparation_time_min"] >= 0]
    cleaned = cleaned[cleaned["carrier_capacity"].between(0, 1)]
    cleaned = cleaned[cleaned["stock_available"].isin([0, 1])]
    return cleaned.reset_index(drop=True)
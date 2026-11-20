"""DAG Airflow pour orchestrer le réentraînement périodique du modèle (TP4).

Ce DAG s'appuie sur `orchestration.retrain_pipeline` (séparé de la CI/CD).
"""
from datetime import datetime, timedelta

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
except ImportError:  # Permet les tests et l'analyse statique sans installer Airflow
    DAG = None
    PythonOperator = None


def _run_retrain_task() -> None:
    """Point d'entrée exécuté par le worker Airflow."""
    from orchestration.retrain_pipeline import main  # pylint: disable=import-outside-toplevel

    main()


if DAG is not None and PythonOperator is not None:
    default_args = {
        "owner": "mlops",
        "depends_on_past": False,
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    }

    with DAG(
        dag_id="retrain_express_delivery_model",
        description="Réentraînement périodique depuis la base analytique MongoDB (ADR-0006)",
        default_args=default_args,
        schedule="@daily",
        start_date=datetime(2026, 10, 29),
        catchup=False,
        tags=["ml", "training", "tp4"],
    ) as dag:
        retrain_task = PythonOperator(
            task_id="retrain_and_promote_model",
            python_callable=_run_retrain_task,
        )

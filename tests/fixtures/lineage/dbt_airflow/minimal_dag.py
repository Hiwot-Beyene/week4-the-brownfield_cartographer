from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

with DAG("minimal_dag", start_date=datetime(2025, 1, 1)) as dag:
    task_a = PythonOperator(task_id="task_a", python_callable=lambda: None)
    task_b = PythonOperator(task_id="task_b", python_callable=lambda: None)
    task_a >> task_b

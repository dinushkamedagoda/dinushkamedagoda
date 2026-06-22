"""MLflow experiment tracking for counterfeit detection runs."""

from __future__ import annotations

import logging
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import mlflow
import mlflow.pyfunc
import numpy as np
from mlflow.tracking import MlflowClient

logger = logging.getLogger(__name__)


class CounterfeitTracker:
    """Wraps MLflow for logging detection runs, metrics, and model artefacts."""

    def __init__(self, tracking_uri: str = "mlruns", experiment_name: str = "counterfeit_detection"):
        mlflow.set_tracking_uri(tracking_uri)
        self.client = MlflowClient()
        self.experiment_name = experiment_name

        experiment = mlflow.get_experiment_by_name(experiment_name)
        if experiment is None:
            self.experiment_id = mlflow.create_experiment(experiment_name)
        else:
            self.experiment_id = experiment.experiment_id

        logger.info(f"MLflow tracking URI: {tracking_uri}, experiment: {experiment_name}")

    @contextmanager
    def start_run(self, run_name: Optional[str] = None, tags: Optional[Dict[str, str]] = None):
        with mlflow.start_run(
            experiment_id=self.experiment_id,
            run_name=run_name,
            tags=tags or {},
        ) as run:
            yield run

    def log_detection_result(
        self,
        run_id: str,
        image_path: str,
        verdict: str,
        confidence: float,
        top_k_scores: List[float],
        ocr_text: str,
        processing_ms: float,
        num_detections: int,
    ):
        with mlflow.start_run(run_id=run_id):
            mlflow.log_param("image_path", image_path)
            mlflow.log_param("num_detections", num_detections)
            mlflow.log_param("ocr_char_count", len(ocr_text))

            mlflow.log_metric("confidence", confidence)
            mlflow.log_metric("processing_time_ms", processing_ms)

            for i, score in enumerate(top_k_scores):
                mlflow.log_metric(f"match_score_top{i+1}", score)

            mlflow.log_param("verdict", verdict)

    def log_batch_evaluation(
        self,
        run_name: str,
        results: List[Dict[str, Any]],
        model_config: Dict[str, Any],
    ):
        with self.start_run(run_name=run_name) as run:
            mlflow.log_params(model_config)

            verdicts = [r["verdict"] for r in results]
            confidences = [r["confidence"] for r in results]
            proc_times = [r["processing_ms"] for r in results]

            mlflow.log_metric("avg_confidence", float(np.mean(confidences)))
            mlflow.log_metric("avg_processing_ms", float(np.mean(proc_times)))
            mlflow.log_metric("counterfeit_rate", verdicts.count("counterfeit") / max(len(verdicts), 1))
            mlflow.log_metric("suspicious_rate", verdicts.count("suspicious") / max(len(verdicts), 1))
            mlflow.log_metric("genuine_rate", verdicts.count("genuine") / max(len(verdicts), 1))
            mlflow.log_metric("total_images", len(results))

            return run.info.run_id

    def log_model_artifacts(self, run_id: str, model_dir: str):
        with mlflow.start_run(run_id=run_id):
            mlflow.log_artifacts(model_dir, artifact_path="model_artifacts")

    def register_model(self, run_id: str, model_name: str, model_uri_suffix: str = "model_artifacts"):
        model_uri = f"runs:/{run_id}/{model_uri_suffix}"
        result = mlflow.register_model(model_uri, model_name)
        logger.info(f"Registered model '{model_name}' version {result.version}")
        return result

    def get_best_run(self, metric: str = "avg_confidence", ascending: bool = False) -> Optional[Dict]:
        runs = mlflow.search_runs(
            experiment_ids=[self.experiment_id],
            order_by=[f"metrics.{metric} {'ASC' if ascending else 'DESC'}"],
            max_results=1,
        )
        if runs.empty:
            return None
        return runs.iloc[0].to_dict()

"""Evaluation script: measure precision, recall, F1 on a labelled dataset."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import yaml
from PIL import Image
from sklearn.metrics import classification_report, confusion_matrix
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))

from mlflow_tracking.tracker import CounterfeitTracker
from models.clip_embedder import CLIPEmbedder
from models.nlp_embedder import NLPEmbedder
from models.ocr_engine import MultilingualOCR
from models.similarity_engine import SimilarityEngine
from models.yolo_detector import YOLODetector
from pipeline.detection_pipeline import CounterfeitDetectionPipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_dataset(dataset_file: str) -> List[Dict]:
    """Load evaluation dataset JSON: [{image_path, label}] where label in [genuine, counterfeit, suspicious]."""
    with open(dataset_file) as f:
        return json.load(f)


def evaluate(dataset_file: str, index_dir: str, config_file: str = "configs/config.yaml"):
    with open(config_file) as f:
        cfg = yaml.safe_load(f)

    device = cfg["system"]["device"]
    yolo = YOLODetector(model_path=cfg["yolo"]["model"], device=device)
    clip_emb = CLIPEmbedder(model_name=cfg["clip"]["model"], device=device)
    ocr = MultilingualOCR(languages=cfg["ocr"]["languages"], use_gpu=cfg["ocr"]["use_gpu"])
    nlp = NLPEmbedder(model_name=cfg["nlp"]["model"], device=device)
    sim = SimilarityEngine.load(index_dir)

    pipeline = CounterfeitDetectionPipeline(
        yolo_detector=yolo, clip_embedder=clip_emb,
        ocr_engine=ocr, nlp_embedder=nlp, similarity_engine=sim,
    )

    tracker = CounterfeitTracker(
        tracking_uri=cfg["mlflow"]["tracking_uri"],
        experiment_name=cfg["mlflow"]["experiment_name"],
    )

    dataset = load_dataset(dataset_file)
    y_true, y_pred = [], []
    raw_results = []

    for item in tqdm(dataset, desc="Evaluating"):
        image = Image.open(item["image_path"]).convert("RGB")
        result = pipeline.analyze(image, image_path=item["image_path"])
        y_true.append(item["label"])
        y_pred.append(result.overall_verdict)
        raw_results.append({
            "verdict": result.overall_verdict,
            "confidence": result.confidence,
            "processing_ms": result.processing_time_ms,
        })

    report = classification_report(y_true, y_pred, output_dict=True)
    cm = confusion_matrix(y_true, y_pred, labels=["genuine", "suspicious", "counterfeit"])

    logger.info("\n" + classification_report(y_true, y_pred))
    logger.info(f"Confusion matrix:\n{cm}")

    run_id = tracker.log_batch_evaluation(
        run_name="evaluation",
        results=raw_results,
        model_config={
            "index_dir": index_dir,
            "counterfeit_threshold": cfg["similarity"]["counterfeit_threshold"],
            "suspicious_threshold": cfg["similarity"]["suspicious_threshold"],
        },
    )

    with tracker.start_run(run_id=run_id):
        import mlflow
        for label, metrics in report.items():
            if isinstance(metrics, dict):
                for metric_name, value in metrics.items():
                    mlflow.log_metric(f"{label}_{metric_name}", value)

    return report, cm


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, help="Path to evaluation JSON")
    parser.add_argument("--index-dir", default="data/embeddings/faiss_index")
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()
    evaluate(args.dataset, args.index_dir, args.config)

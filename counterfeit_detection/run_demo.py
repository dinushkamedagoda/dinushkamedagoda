"""
Standalone demo: registers synthetic authentic products, then analyses
a test image and prints a counterfeit verdict.

Usage:
    python run_demo.py --image path/to/test_product.jpg
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def build_pipeline(cfg: dict):
    from models.clip_embedder import CLIPEmbedder
    from models.nlp_embedder import NLPEmbedder
    from models.ocr_engine import MultilingualOCR
    from models.similarity_engine import SimilarityEngine
    from models.yolo_detector import YOLODetector
    from pipeline.detection_pipeline import CounterfeitDetectionPipeline

    device = cfg["system"]["device"]
    yolo   = YOLODetector(model_path=cfg["yolo"]["model"], device=device)
    clip   = CLIPEmbedder(model_name=cfg["clip"]["model"], device=device)
    ocr    = MultilingualOCR(languages=cfg["ocr"]["languages"], use_gpu=cfg["ocr"]["use_gpu"])
    nlp    = NLPEmbedder(model_name=cfg["nlp"]["model"], device=device)
    sim    = SimilarityEngine(
        image_dim=cfg["clip"]["embedding_dim"],
        text_dim=nlp.embedding_dim,
        **{k: cfg["similarity"][k] for k in
           ["image_weight","text_weight","logo_weight",
            "counterfeit_threshold","suspicious_threshold"]},
    )
    return CounterfeitDetectionPipeline(yolo, clip, ocr, nlp, sim), clip, nlp, ocr


def register_synthetic_reference(pipeline, clip, nlp, ocr):
    """Create a synthetic 'genuine' reference product from a blank coloured image."""
    from models.similarity_engine import ProductEntry

    ref_image = Image.new("RGB", (224, 224), color=(200, 50, 50))
    draw = ImageDraw.Draw(ref_image)
    draw.text((10, 100), "GENUINE BRAND", fill="white")

    img_emb = clip.embed_single(ref_image)
    txt_emb = nlp.embed_single("GENUINE BRAND authentic product label")

    entry = ProductEntry(
        product_id="genuine_001",
        brand="GenuineBrand",
        category="demo",
        image_embedding=img_emb,
        text_embedding=txt_emb,
        metadata={"source": "synthetic_reference"},
    )
    pipeline.sim.add_product(entry)
    logger.info("Registered 1 synthetic reference product")


def print_report(result):
    print("\n" + "=" * 55)
    print("  COUNTERFEIT DETECTION REPORT")
    print("=" * 55)
    verdict_colour = {"counterfeit": "RED", "suspicious": "YELLOW", "genuine": "GREEN", "unknown": "GREY"}
    print(f"  Verdict     : {result.overall_verdict.upper()} [{verdict_colour.get(result.overall_verdict,'?')}]")
    print(f"  Confidence  : {result.confidence:.2%}")
    print(f"  OCR text    : {result.ocr_result.full_text[:80]!r}")
    print(f"  OCR langs   : {result.ocr_result.languages_detected}")
    print(f"  Detections  : {len(result.detections)} objects")
    print(f"  Time        : {result.processing_time_ms:.1f} ms")
    print()
    if result.matches:
        print("  TOP MATCHES:")
        for i, m in enumerate(result.matches[:3], 1):
            print(f"    {i}. {m.brand}/{m.product_id} — combined={m.combined_score:.3f} [{m.verdict}]")
    print("=" * 55 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Counterfeit detection demo")
    parser.add_argument("--image", required=True, help="Path to product image")
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    pipeline, clip, nlp, ocr = build_pipeline(cfg)
    register_synthetic_reference(pipeline, clip, nlp, ocr)

    image = Image.open(args.image).convert("RGB")
    result = pipeline.analyze(image, image_path=args.image)
    print_report(result)


if __name__ == "__main__":
    main()

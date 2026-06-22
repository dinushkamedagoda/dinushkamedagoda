"""FastAPI REST API for counterfeit product detection."""

from __future__ import annotations

import io
import logging
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image
from pydantic import BaseModel

# Lazy import of pipeline components to allow API startup without GPU
_pipeline = None
_tracker = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Counterfeit Detection API",
    description="AI-powered system using YOLO, CLIP, OCR, NLP and similarity search to detect counterfeit products.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class DetectionBox(BaseModel):
    bbox: List[float]
    confidence: float
    class_name: str


class MatchResult(BaseModel):
    product_id: str
    brand: str
    category: str
    image_score: float
    text_score: float
    logo_score: float
    combined_score: float
    verdict: str


class AnalysisResponse(BaseModel):
    request_id: str
    verdict: str
    confidence: float
    detected_text: str
    ocr_languages: List[str]
    detections: List[DetectionBox]
    top_matches: List[MatchResult]
    processing_time_ms: float


class HealthResponse(BaseModel):
    status: str
    pipeline_ready: bool
    total_reference_products: int


# ─── Startup / Shutdown ───────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    global _pipeline, _tracker
    logger.info("Initialising detection pipeline…")
    try:
        config = _load_config()
        _pipeline, _tracker = _build_pipeline(config)
        logger.info("Pipeline ready.")
    except Exception as e:
        logger.error(f"Pipeline init failed: {e}")


def _load_config() -> dict:
    cfg_path = Path(__file__).parent.parent / "configs" / "config.yaml"
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def _build_pipeline(cfg: dict):
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from mlflow_tracking.tracker import CounterfeitTracker
    from models.clip_embedder import CLIPEmbedder
    from models.nlp_embedder import NLPEmbedder
    from models.ocr_engine import MultilingualOCR
    from models.similarity_engine import SimilarityEngine
    from models.yolo_detector import YOLODetector
    from pipeline.detection_pipeline import CounterfeitDetectionPipeline

    device = cfg["system"]["device"]

    yolo = YOLODetector(
        model_path=cfg["yolo"]["model"],
        confidence=cfg["yolo"]["confidence"],
        iou_threshold=cfg["yolo"]["iou_threshold"],
        img_size=cfg["yolo"]["img_size"],
        device=device,
    )
    clip_emb = CLIPEmbedder(model_name=cfg["clip"]["model"], device=device)
    ocr = MultilingualOCR(languages=cfg["ocr"]["languages"], use_gpu=cfg["ocr"]["use_gpu"])
    nlp = NLPEmbedder(model_name=cfg["nlp"]["model"], device=device)

    sim_cfg = cfg["similarity"]
    sim_engine = SimilarityEngine(
        image_dim=cfg["clip"]["embedding_dim"],
        text_dim=nlp.embedding_dim,
        image_weight=sim_cfg["image_weight"],
        text_weight=sim_cfg["text_weight"],
        logo_weight=sim_cfg["logo_weight"],
        counterfeit_threshold=sim_cfg["counterfeit_threshold"],
        suspicious_threshold=sim_cfg["suspicious_threshold"],
    )

    # Load persisted index if exists
    index_dir = Path(cfg["paths"]["embeddings_dir"]) / "faiss_index"
    if index_dir.exists():
        sim_engine = SimilarityEngine.load(str(index_dir))

    pipeline = CounterfeitDetectionPipeline(
        yolo_detector=yolo,
        clip_embedder=clip_emb,
        ocr_engine=ocr,
        nlp_embedder=nlp,
        similarity_engine=sim_engine,
    )

    tracker = CounterfeitTracker(
        tracking_uri=cfg["mlflow"]["tracking_uri"],
        experiment_name=cfg["mlflow"]["experiment_name"],
    )

    return pipeline, tracker


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health():
    ready = _pipeline is not None
    total = len(_pipeline.sim._entries) if ready else 0
    return HealthResponse(status="ok", pipeline_ready=ready, total_reference_products=total)


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_product(file: UploadFile = File(...)):
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not ready")

    allowed = {"jpg", "jpeg", "png", "webp"}
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {ext}")

    contents = await file.read()
    try:
        image = Image.open(io.BytesIO(contents))
    except Exception:
        raise HTTPException(status_code=400, detail="Cannot decode image")

    request_id = str(uuid.uuid4())
    result = _pipeline.analyze(image, image_path=file.filename or "", top_k=5)

    # Log to MLflow asynchronously (fire and forget style for this demo)
    try:
        with _tracker.start_run(run_name=f"infer_{request_id[:8]}"):
            import mlflow
            mlflow.log_param("verdict", result.overall_verdict)
            mlflow.log_metric("confidence", result.confidence)
            mlflow.log_metric("processing_ms", result.processing_time_ms)
    except Exception as e:
        logger.warning(f"MLflow logging failed: {e}")

    return AnalysisResponse(
        request_id=request_id,
        verdict=result.overall_verdict,
        confidence=round(result.confidence, 4),
        detected_text=result.ocr_result.full_text[:500],
        ocr_languages=result.ocr_result.languages_detected,
        detections=[
            DetectionBox(
                bbox=d.bbox,
                confidence=round(d.confidence, 4),
                class_name=d.class_name,
            )
            for d in result.detections
        ],
        top_matches=[
            MatchResult(
                product_id=m.product_id,
                brand=m.brand,
                category=m.category,
                image_score=round(m.image_score, 4),
                text_score=round(m.text_score, 4),
                logo_score=round(m.logo_score, 4),
                combined_score=round(m.combined_score, 4),
                verdict=m.verdict,
            )
            for m in result.matches
        ],
        processing_time_ms=round(result.processing_time_ms, 1),
    )


@app.post("/register")
async def register_authentic_product(
    file: UploadFile = File(...),
    product_id: str = "",
    brand: str = "",
    category: str = "",
):
    """Register a reference authentic product image into the FAISS index."""
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not ready")
    if not product_id:
        raise HTTPException(status_code=400, detail="product_id is required")

    contents = await file.read()
    image = Image.open(io.BytesIO(contents)).convert("RGB")

    img_emb = _pipeline.clip.embed_single(image)
    ocr_result = _pipeline.ocr.read(image)
    text = ocr_result.full_text or f"{brand} {category}"
    txt_emb = _pipeline.nlp.embed_single(text)

    from models.similarity_engine import ProductEntry
    entry = ProductEntry(
        product_id=product_id,
        brand=brand,
        category=category,
        image_embedding=img_emb,
        text_embedding=txt_emb,
        metadata={"ocr_text": ocr_result.full_text},
    )
    _pipeline.sim.add_product(entry)

    return JSONResponse({"status": "registered", "product_id": product_id, "total": len(_pipeline.sim._entries)})

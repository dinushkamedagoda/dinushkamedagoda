"""End-to-end counterfeit detection pipeline."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PIL import Image

from models.clip_embedder import CLIPEmbedder
from models.nlp_embedder import NLPEmbedder
from models.ocr_engine import DocumentOCR, MultilingualOCR
from models.similarity_engine import SimilarityEngine, SimilarityMatch
from models.yolo_detector import Detection, YOLODetector

logger = logging.getLogger(__name__)


@dataclass
class ProductAnalysis:
    image_path: str
    detections: List[Detection]
    ocr_result: DocumentOCR
    image_embedding: np.ndarray
    text_embedding: np.ndarray
    logo_embedding: Optional[np.ndarray]
    matches: List[SimilarityMatch]
    top_match: Optional[SimilarityMatch]
    overall_verdict: str  # "genuine" | "suspicious" | "counterfeit" | "unknown"
    confidence: float
    processing_time_ms: float
    metadata: Dict = field(default_factory=dict)


class CounterfeitDetectionPipeline:
    """
    Full pipeline:
      1. YOLO  → locate product regions & logos
      2. CLIP  → embed the full image + detected crops
      3. EasyOCR → extract multilingual text
      4. NLP   → embed extracted text
      5. FAISS → search reference database
      6. Score fusion → verdict
    """

    def __init__(
        self,
        yolo_detector: YOLODetector,
        clip_embedder: CLIPEmbedder,
        ocr_engine: MultilingualOCR,
        nlp_embedder: NLPEmbedder,
        similarity_engine: SimilarityEngine,
        logo_class_names: Optional[List[str]] = None,
    ):
        self.yolo = yolo_detector
        self.clip = clip_embedder
        self.ocr = ocr_engine
        self.nlp = nlp_embedder
        self.sim = similarity_engine
        self.logo_class_names = set(logo_class_names or ["logo", "brand_mark", "label"])

    def analyze(self, image: Image.Image, image_path: str = "", top_k: int = 5) -> ProductAnalysis:
        """Analyse a single product image end-to-end."""
        t0 = time.perf_counter()
        image = image.convert("RGB")

        # Stage 1: Object detection
        detections = self.yolo.detect(image)

        # Stage 2: Logo crop embedding
        logo_embedding: Optional[np.ndarray] = None
        logo_crops = [d.crop for d in detections if d.class_name in self.logo_class_names and d.crop]
        if logo_crops:
            logo_embs = self.clip.embed_images(logo_crops)
            logo_embedding = logo_embs.mean(axis=0)
            logo_embedding = logo_embedding / (np.linalg.norm(logo_embedding) + 1e-8)

        # Stage 3: Full-image CLIP embedding
        image_embedding = self.clip.embed_single(image)

        # Stage 4: OCR
        ocr_result = self.ocr.read(image)

        # Stage 5: NLP text embedding
        text_to_embed = ocr_result.full_text if ocr_result.full_text.strip() else "unknown product"
        text_embedding = self.nlp.embed_single(text_to_embed)

        # Stage 6: Similarity search
        matches = self.sim.search(
            image_embedding=image_embedding,
            text_embedding=text_embedding,
            logo_embedding=logo_embedding,
            top_k=top_k,
        )

        top_match = matches[0] if matches else None
        overall_verdict, confidence = self._resolve_verdict(matches)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(f"Analysis complete in {elapsed_ms:.1f}ms — verdict: {overall_verdict} ({confidence:.2f})")

        return ProductAnalysis(
            image_path=image_path,
            detections=detections,
            ocr_result=ocr_result,
            image_embedding=image_embedding,
            text_embedding=text_embedding,
            logo_embedding=logo_embedding,
            matches=matches,
            top_match=top_match,
            overall_verdict=overall_verdict,
            confidence=confidence,
            processing_time_ms=elapsed_ms,
        )

    def analyze_batch(self, images: List[Image.Image], paths: Optional[List[str]] = None) -> List[ProductAnalysis]:
        paths = paths or [""] * len(images)
        return [self.analyze(img, path) for img, path in zip(images, paths)]

    def _resolve_verdict(self, matches: List[SimilarityMatch]) -> tuple[str, float]:
        if not matches:
            return "unknown", 0.0

        top = matches[0]
        # Weight votes from top-3 matches
        weighted_verdicts: Dict[str, float] = {"genuine": 0.0, "suspicious": 0.0, "counterfeit": 0.0}
        weights = [1.0, 0.5, 0.25]
        for match, w in zip(matches[:3], weights):
            weighted_verdicts[match.verdict] += w * match.combined_score

        verdict = max(weighted_verdicts, key=weighted_verdicts.__getitem__)
        confidence = top.combined_score
        return verdict, confidence

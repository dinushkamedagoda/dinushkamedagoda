"""Similarity engine combining image, text, and logo embeddings with FAISS index."""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import faiss
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ProductEntry:
    product_id: str
    brand: str
    category: str
    image_embedding: np.ndarray
    text_embedding: np.ndarray
    logo_embedding: Optional[np.ndarray] = None
    metadata: Dict = field(default_factory=dict)


@dataclass
class SimilarityMatch:
    product_id: str
    brand: str
    category: str
    image_score: float
    text_score: float
    logo_score: float
    combined_score: float
    verdict: str  # "genuine" | "suspicious" | "counterfeit"
    metadata: Dict = field(default_factory=dict)


class SimilarityEngine:
    """FAISS-backed similarity search over image + text + logo embeddings."""

    def __init__(
        self,
        image_dim: int = 512,
        text_dim: int = 384,
        image_weight: float = 0.5,
        text_weight: float = 0.3,
        logo_weight: float = 0.2,
        counterfeit_threshold: float = 0.85,
        suspicious_threshold: float = 0.70,
    ):
        self.image_dim = image_dim
        self.text_dim = text_dim
        self.image_weight = image_weight
        self.text_weight = text_weight
        self.logo_weight = logo_weight
        self.counterfeit_threshold = counterfeit_threshold
        self.suspicious_threshold = suspicious_threshold

        self._entries: List[ProductEntry] = []
        self._image_index = faiss.IndexFlatIP(image_dim)  # inner product on L2-normalised = cosine
        self._text_index = faiss.IndexFlatIP(text_dim)

    def add_product(self, entry: ProductEntry):
        """Register an authentic product reference."""
        self._entries.append(entry)
        img_emb = entry.image_embedding.astype(np.float32).reshape(1, -1)
        txt_emb = entry.text_embedding.astype(np.float32).reshape(1, -1)
        faiss.normalize_L2(img_emb)
        faiss.normalize_L2(txt_emb)
        self._image_index.add(img_emb)
        self._text_index.add(txt_emb)
        logger.debug(f"Added product {entry.product_id} (total: {len(self._entries)})")

    def add_products_batch(self, entries: List[ProductEntry]):
        for e in entries:
            self.add_product(e)

    def search(
        self,
        image_embedding: np.ndarray,
        text_embedding: np.ndarray,
        logo_embedding: Optional[np.ndarray] = None,
        top_k: int = 5,
    ) -> List[SimilarityMatch]:
        """Find the top-k most similar authentic products."""
        if len(self._entries) == 0:
            return []

        k = min(top_k, len(self._entries))

        img_q = image_embedding.astype(np.float32).reshape(1, -1)
        txt_q = text_embedding.astype(np.float32).reshape(1, -1)
        faiss.normalize_L2(img_q)
        faiss.normalize_L2(txt_q)

        img_scores, img_indices = self._image_index.search(img_q, k)
        txt_scores, txt_indices = self._text_index.search(txt_q, k)

        candidate_indices = set(img_indices[0].tolist()) | set(txt_indices[0].tolist())
        candidate_indices.discard(-1)

        img_score_map = {int(idx): float(score) for idx, score in zip(img_indices[0], img_scores[0])}
        txt_score_map = {int(idx): float(score) for idx, score in zip(txt_indices[0], txt_scores[0])}

        matches: List[SimilarityMatch] = []
        for idx in candidate_indices:
            entry = self._entries[idx]
            img_s = max(img_score_map.get(idx, 0.0), 0.0)
            txt_s = max(txt_score_map.get(idx, 0.0), 0.0)

            logo_s = 0.0
            if logo_embedding is not None and entry.logo_embedding is not None:
                a = logo_embedding.astype(np.float32)
                b = entry.logo_embedding.astype(np.float32)
                logo_s = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))
                logo_s = max(logo_s, 0.0)
                combined = (
                    self.image_weight * img_s
                    + self.text_weight * txt_s
                    + self.logo_weight * logo_s
                )
            else:
                effective_img_w = self.image_weight / (self.image_weight + self.text_weight)
                effective_txt_w = self.text_weight / (self.image_weight + self.text_weight)
                combined = effective_img_w * img_s + effective_txt_w * txt_s

            verdict = self._classify(combined)
            matches.append(SimilarityMatch(
                product_id=entry.product_id,
                brand=entry.brand,
                category=entry.category,
                image_score=img_s,
                text_score=txt_s,
                logo_score=logo_s,
                combined_score=combined,
                verdict=verdict,
                metadata=entry.metadata,
            ))

        matches.sort(key=lambda m: m.combined_score, reverse=True)
        return matches[:top_k]

    def _classify(self, score: float) -> str:
        if score >= self.counterfeit_threshold:
            return "counterfeit"
        if score >= self.suspicious_threshold:
            return "suspicious"
        return "genuine"

    def save(self, path: str):
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._image_index, str(p / "image.index"))
        faiss.write_index(self._text_index, str(p / "text.index"))
        with open(p / "entries.pkl", "wb") as f:
            pickle.dump(self._entries, f)
        logger.info(f"Saved similarity engine to {p}")

    @classmethod
    def load(cls, path: str, **kwargs) -> "SimilarityEngine":
        p = Path(path)
        engine = cls(**kwargs)
        engine._image_index = faiss.read_index(str(p / "image.index"))
        engine._text_index = faiss.read_index(str(p / "text.index"))
        with open(p / "entries.pkl", "rb") as f:
            engine._entries = pickle.load(f)
        logger.info(f"Loaded similarity engine from {p} ({len(engine._entries)} products)")
        return engine

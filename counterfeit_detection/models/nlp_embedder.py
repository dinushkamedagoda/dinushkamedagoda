"""Multilingual NLP text embedding using sentence-transformers."""

from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class NLPEmbedder:
    """Multilingual sentence embedding model for product text comparison."""

    def __init__(
        self,
        model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        device: Optional[str] = None,
        max_length: int = 512,
    ):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.max_length = max_length
        logger.info(f"Loading NLP embedder {model_name} on {self.device}")
        self.model = SentenceTransformer(model_name, device=self.device)
        self.model.max_seq_length = max_length
        self.embedding_dim = self.model.get_sentence_embedding_dimension()

    def embed(self, texts: List[str], batch_size: int = 64, normalize: bool = True) -> np.ndarray:
        """Embed a list of texts into dense vectors."""
        if not texts:
            return np.empty((0, self.embedding_dim))

        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=normalize,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return embeddings

    def embed_single(self, text: str) -> np.ndarray:
        return self.embed([text])[0]

    def similarity(self, text_a: str, text_b: str) -> float:
        """Cosine similarity between two texts."""
        embs = self.embed([text_a, text_b])
        return float(np.dot(embs[0], embs[1]))

    def batch_similarity(self, queries: List[str], candidates: List[str]) -> np.ndarray:
        """Return (len(queries), len(candidates)) similarity matrix."""
        q_embs = self.embed(queries)
        c_embs = self.embed(candidates)
        return q_embs @ c_embs.T

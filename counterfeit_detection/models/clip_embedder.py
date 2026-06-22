"""CLIP-based image embedding model."""

from __future__ import annotations

import logging
from typing import List, Optional, Union

import clip
import numpy as np
import torch
from PIL import Image

logger = logging.getLogger(__name__)


class CLIPEmbedder:
    """Generates visual embeddings using OpenAI CLIP."""

    def __init__(self, model_name: str = "ViT-B/32", device: Optional[str] = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Loading CLIP model {model_name} on {self.device}")

        self.model, self.preprocess = clip.load(model_name, device=self.device)
        self.model.eval()
        self.embedding_dim = self.model.visual.output_dim

    @torch.no_grad()
    def embed_images(self, images: List[Image.Image], batch_size: int = 32) -> np.ndarray:
        """Embed a list of PIL images into L2-normalised vectors."""
        all_embeddings: List[np.ndarray] = []

        for i in range(0, len(images), batch_size):
            batch = images[i : i + batch_size]
            tensors = torch.stack([self.preprocess(img) for img in batch]).to(self.device)
            embeddings = self.model.encode_image(tensors)
            embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)
            all_embeddings.append(embeddings.cpu().numpy())

        return np.vstack(all_embeddings) if all_embeddings else np.empty((0, self.embedding_dim))

    @torch.no_grad()
    def embed_texts(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """Embed a list of text strings into L2-normalised vectors."""
        all_embeddings: List[np.ndarray] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            tokens = clip.tokenize(batch, truncate=True).to(self.device)
            embeddings = self.model.encode_text(tokens)
            embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)
            all_embeddings.append(embeddings.cpu().numpy())

        return np.vstack(all_embeddings) if all_embeddings else np.empty((0, self.embedding_dim))

    def embed_single(self, image: Image.Image) -> np.ndarray:
        return self.embed_images([image])[0]

    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))

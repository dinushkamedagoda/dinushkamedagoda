"""Unit and integration tests for the counterfeit detection pipeline."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def dummy_image():
    img = Image.new("RGB", (224, 224), color=(100, 150, 200))
    return img


@pytest.fixture
def dummy_image_embedding():
    emb = np.random.rand(512).astype(np.float32)
    return emb / np.linalg.norm(emb)


@pytest.fixture
def dummy_text_embedding():
    emb = np.random.rand(384).astype(np.float32)
    return emb / np.linalg.norm(emb)


# ─── SimilarityEngine tests ───────────────────────────────────────────────────

class TestSimilarityEngine:
    def test_empty_search_returns_empty(self, dummy_image_embedding, dummy_text_embedding):
        from models.similarity_engine import SimilarityEngine
        engine = SimilarityEngine(image_dim=512, text_dim=384)
        results = engine.search(dummy_image_embedding, dummy_text_embedding)
        assert results == []

    def test_add_and_search(self, dummy_image_embedding, dummy_text_embedding):
        from models.similarity_engine import ProductEntry, SimilarityEngine
        engine = SimilarityEngine(image_dim=512, text_dim=384)

        entry = ProductEntry(
            product_id="prod_001",
            brand="TestBrand",
            category="watches",
            image_embedding=dummy_image_embedding.copy(),
            text_embedding=dummy_text_embedding.copy(),
        )
        engine.add_product(entry)

        results = engine.search(dummy_image_embedding, dummy_text_embedding, top_k=1)
        assert len(results) == 1
        assert results[0].product_id == "prod_001"
        assert results[0].combined_score > 0.9

    def test_counterfeit_verdict_on_high_similarity(self, dummy_image_embedding, dummy_text_embedding):
        from models.similarity_engine import ProductEntry, SimilarityEngine
        engine = SimilarityEngine(
            image_dim=512, text_dim=384,
            counterfeit_threshold=0.85, suspicious_threshold=0.70
        )
        entry = ProductEntry(
            product_id="brand_001", brand="LuxBrand", category="bags",
            image_embedding=dummy_image_embedding.copy(),
            text_embedding=dummy_text_embedding.copy(),
        )
        engine.add_product(entry)

        results = engine.search(dummy_image_embedding, dummy_text_embedding)
        assert results[0].verdict == "counterfeit"
        assert results[0].combined_score >= 0.85

    def test_classify_thresholds(self):
        from models.similarity_engine import SimilarityEngine
        engine = SimilarityEngine(counterfeit_threshold=0.85, suspicious_threshold=0.70)
        assert engine._classify(0.90) == "counterfeit"
        assert engine._classify(0.75) == "suspicious"
        assert engine._classify(0.50) == "genuine"

    def test_save_and_load(self, tmp_path, dummy_image_embedding, dummy_text_embedding):
        from models.similarity_engine import ProductEntry, SimilarityEngine
        engine = SimilarityEngine(image_dim=512, text_dim=384)
        entry = ProductEntry(
            product_id="p1", brand="B", category="C",
            image_embedding=dummy_image_embedding.copy(),
            text_embedding=dummy_text_embedding.copy(),
        )
        engine.add_product(entry)
        engine.save(str(tmp_path / "index"))

        loaded = SimilarityEngine.load(str(tmp_path / "index"))
        assert len(loaded._entries) == 1
        results = loaded.search(dummy_image_embedding, dummy_text_embedding)
        assert len(results) == 1


# ─── CLIPEmbedder tests ───────────────────────────────────────────────────────

class TestCLIPEmbedder:
    def test_embed_returns_normalised_vector(self, dummy_image):
        from models.clip_embedder import CLIPEmbedder
        embedder = CLIPEmbedder(model_name="ViT-B/32", device="cpu")
        emb = embedder.embed_single(dummy_image)
        assert emb.shape == (512,)
        np.testing.assert_almost_equal(np.linalg.norm(emb), 1.0, decimal=5)

    def test_text_embed_shape(self):
        from models.clip_embedder import CLIPEmbedder
        embedder = CLIPEmbedder(model_name="ViT-B/32", device="cpu")
        emb = embedder.embed_texts(["a product label"])
        assert emb.shape == (1, 512)

    def test_empty_batch(self):
        from models.clip_embedder import CLIPEmbedder
        embedder = CLIPEmbedder(model_name="ViT-B/32", device="cpu")
        emb = embedder.embed_images([])
        assert emb.shape[0] == 0


# ─── NLPEmbedder tests ────────────────────────────────────────────────────────

class TestNLPEmbedder:
    def test_embed_returns_correct_shape(self):
        from models.nlp_embedder import NLPEmbedder
        emb = NLPEmbedder(device="cpu")
        result = emb.embed(["hello world", "fake product"])
        assert result.shape[0] == 2
        assert result.shape[1] == emb.embedding_dim

    def test_similarity_same_text(self):
        from models.nlp_embedder import NLPEmbedder
        emb = NLPEmbedder(device="cpu")
        sim = emb.similarity("Rolex watch genuine", "Rolex watch genuine")
        assert sim > 0.99

    def test_multilingual(self):
        from models.nlp_embedder import NLPEmbedder
        emb = NLPEmbedder(device="cpu")
        # Chinese + English embeddings of similar concepts should be similar
        en = emb.embed_single("luxury handbag")
        zh = emb.embed_single("奢侈品手袋")
        sim = float(np.dot(en, zh))
        assert sim > 0.3  # cross-lingual alignment


# ─── Pipeline integration test ────────────────────────────────────────────────

class TestPipeline:
    def test_analyze_returns_result(self, dummy_image):
        """Integration test using mocked sub-models."""
        from pipeline.detection_pipeline import CounterfeitDetectionPipeline
        from models.similarity_engine import SimilarityEngine

        yolo = MagicMock()
        yolo.detect.return_value = []

        clip_emb = MagicMock()
        img_emb = np.random.rand(512).astype(np.float32)
        img_emb /= np.linalg.norm(img_emb)
        clip_emb.embed_single.return_value = img_emb
        clip_emb.embed_images.return_value = np.empty((0, 512))

        ocr = MagicMock()
        from models.ocr_engine import DocumentOCR
        ocr.read.return_value = DocumentOCR(full_text="Test Product Brand", avg_confidence=0.9)

        nlp = MagicMock()
        txt_emb = np.random.rand(384).astype(np.float32)
        txt_emb /= np.linalg.norm(txt_emb)
        nlp.embed_single.return_value = txt_emb
        nlp.embedding_dim = 384

        sim = SimilarityEngine(image_dim=512, text_dim=384)

        pipeline = CounterfeitDetectionPipeline(
            yolo_detector=yolo,
            clip_embedder=clip_emb,
            ocr_engine=ocr,
            nlp_embedder=nlp,
            similarity_engine=sim,
        )

        result = pipeline.analyze(dummy_image)
        assert result.overall_verdict == "unknown"
        assert result.processing_time_ms > 0
        assert result.ocr_result.full_text == "Test Product Brand"

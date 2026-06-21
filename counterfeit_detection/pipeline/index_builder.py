"""Build and persist the FAISS reference database from a directory of authentic product images."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml
from PIL import Image
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.clip_embedder import CLIPEmbedder
from models.nlp_embedder import NLPEmbedder
from models.ocr_engine import MultilingualOCR
from models.similarity_engine import ProductEntry, SimilarityEngine
from mlflow_tracking.tracker import CounterfeitTracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_config(path: str = "configs/config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def build_index(
    image_dir: str,
    metadata_file: Optional[str],
    output_dir: str,
    cfg: dict,
):
    """
    image_dir: directory of authentic product images (jpg/png)
    metadata_file: optional JSON mapping filename -> {product_id, brand, category}
    output_dir: where to save the FAISS index
    """
    device = cfg["system"]["device"]

    clip_emb = CLIPEmbedder(model_name=cfg["clip"]["model"], device=device)
    nlp_emb = NLPEmbedder(model_name=cfg["nlp"]["model"], device=device)
    ocr = MultilingualOCR(languages=cfg["ocr"]["languages"], use_gpu=cfg["ocr"]["use_gpu"])
    sim = SimilarityEngine(
        image_dim=cfg["clip"]["embedding_dim"],
        text_dim=nlp_emb.embedding_dim,
        **{k: cfg["similarity"][k] for k in
           ["image_weight", "text_weight", "logo_weight",
            "counterfeit_threshold", "suspicious_threshold"]},
    )

    tracker = CounterfeitTracker(
        tracking_uri=cfg["mlflow"]["tracking_uri"],
        experiment_name=cfg["mlflow"]["experiment_name"],
    )

    metadata: dict = {}
    if metadata_file and Path(metadata_file).exists():
        with open(metadata_file) as f:
            metadata = json.load(f)

    image_paths = list(Path(image_dir).glob("**/*.jpg")) + list(Path(image_dir).glob("**/*.png"))
    logger.info(f"Found {len(image_paths)} images in {image_dir}")

    with tracker.start_run(run_name="index_build") as run:
        import mlflow
        mlflow.log_param("image_dir", image_dir)
        mlflow.log_param("num_images", len(image_paths))
        mlflow.log_params({k: cfg["similarity"][k] for k in
                           ["image_weight", "text_weight", "logo_weight"]})

        for img_path in tqdm(image_paths, desc="Indexing"):
            fname = img_path.name
            meta = metadata.get(fname, {})
            product_id = meta.get("product_id", img_path.stem)
            brand = meta.get("brand", "unknown")
            category = meta.get("category", "unknown")

            try:
                image = Image.open(img_path).convert("RGB")
                img_emb = clip_emb.embed_single(image)
                ocr_result = ocr.read(image)
                text = ocr_result.full_text or f"{brand} {category}"
                txt_emb = nlp_emb.embed_single(text)

                entry = ProductEntry(
                    product_id=product_id,
                    brand=brand,
                    category=category,
                    image_embedding=img_emb,
                    text_embedding=txt_emb,
                    metadata={"source": str(img_path), "ocr": ocr_result.full_text},
                )
                sim.add_product(entry)
            except Exception as e:
                logger.warning(f"Failed to process {img_path}: {e}")

        sim.save(output_dir)
        mlflow.log_metric("total_indexed", len(sim._entries))
        mlflow.log_artifacts(output_dir, artifact_path="faiss_index")
        logger.info(f"Index saved to {output_dir} with {len(sim._entries)} products")

    return sim


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build FAISS reference index")
    parser.add_argument("--image-dir", required=True, help="Directory of authentic product images")
    parser.add_argument("--metadata", default=None, help="JSON metadata file")
    parser.add_argument("--output-dir", default="data/embeddings/faiss_index")
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    build_index(args.image_dir, args.metadata, args.output_dir, cfg)

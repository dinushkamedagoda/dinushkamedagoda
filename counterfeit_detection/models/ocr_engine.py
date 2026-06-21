"""Multilingual OCR engine using EasyOCR."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import easyocr
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Language groups for reader reuse
_LANG_GROUPS: Dict[str, List[str]] = {
    "latin": ["en", "fr", "de", "es", "it", "pt"],
    "cjk": ["ch_sim", "ch_tra", "ja", "ko"],
    "arabic": ["ar"],
    "devanagari": ["hi"],
}


@dataclass
class OCRResult:
    text: str
    confidence: float
    bbox: List[List[int]]  # [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
    language_hint: Optional[str] = None


@dataclass
class DocumentOCR:
    raw_results: List[OCRResult] = field(default_factory=list)
    full_text: str = ""
    languages_detected: List[str] = field(default_factory=list)
    avg_confidence: float = 0.0


class MultilingualOCR:
    """Multilingual OCR using EasyOCR with dynamic language group loading."""

    def __init__(self, languages: Optional[List[str]] = None, use_gpu: bool = True):
        self.use_gpu = use_gpu
        self.languages = languages or ["en", "ch_sim", "ar", "fr", "de", "es", "ja", "ko", "hi"]
        self._readers: Dict[str, easyocr.Reader] = {}
        self._init_readers()

    def _init_readers(self):
        for group_name, lang_list in _LANG_GROUPS.items():
            active = [l for l in lang_list if l in self.languages]
            if not active:
                continue
            logger.info(f"Initialising OCR reader for group '{group_name}': {active}")
            try:
                reader = easyocr.Reader(active, gpu=self.use_gpu)
                for lang in active:
                    self._readers[lang] = reader
            except Exception as e:
                logger.warning(f"Failed to initialise OCR group {group_name}: {e}")

    def _image_to_np(self, image: Image.Image) -> np.ndarray:
        return np.array(image.convert("RGB"))

    def read(self, image: Image.Image, detail: int = 1) -> DocumentOCR:
        """Extract text from an image using all configured language readers."""
        img_np = self._image_to_np(image)
        seen_texts: Dict[str, OCRResult] = {}

        used_readers = set()
        for lang, reader in self._readers.items():
            reader_id = id(reader)
            if reader_id in used_readers:
                continue
            used_readers.add(reader_id)

            try:
                raw = reader.readtext(img_np, detail=detail, paragraph=False)
                for bbox, text, conf in raw:
                    text = text.strip()
                    if not text or conf < 0.3:
                        continue
                    key = text.lower()
                    if key not in seen_texts or seen_texts[key].confidence < conf:
                        seen_texts[key] = OCRResult(
                            text=text,
                            confidence=conf,
                            bbox=bbox,
                            language_hint=lang,
                        )
            except Exception as e:
                logger.warning(f"OCR reader failed for lang {lang}: {e}")

        results = sorted(seen_texts.values(), key=lambda r: r.confidence, reverse=True)
        full_text = " ".join(r.text for r in results)
        avg_conf = np.mean([r.confidence for r in results]) if results else 0.0
        langs_detected = list({r.language_hint for r in results if r.language_hint})

        return DocumentOCR(
            raw_results=results,
            full_text=full_text,
            languages_detected=langs_detected,
            avg_confidence=float(avg_conf),
        )

    def read_batch(self, images: List[Image.Image]) -> List[DocumentOCR]:
        return [self.read(img) for img in images]

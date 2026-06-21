"""YOLO-based product region detector."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
import torch
from PIL import Image
from ultralytics import YOLO

logger = logging.getLogger(__name__)


@dataclass
class Detection:
    bbox: List[float]  # [x1, y1, x2, y2] normalized
    confidence: float
    class_id: int
    class_name: str
    crop: Optional[Image.Image] = None


class YOLODetector:
    """Detects product regions and logos using YOLOv8."""

    def __init__(self, model_path: str = "yolov8n.pt", confidence: float = 0.5,
                 iou_threshold: float = 0.45, img_size: int = 640,
                 device: Optional[str] = None):
        self.confidence = confidence
        self.iou_threshold = iou_threshold
        self.img_size = img_size
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        logger.info(f"Loading YOLO model from {model_path} on {self.device}")
        self.model = YOLO(model_path)
        self.model.to(self.device)

    def detect(self, image: Image.Image, classes: Optional[List[int]] = None) -> List[Detection]:
        """Run detection on a PIL image and return bounding boxes with crops."""
        results = self.model(
            image,
            conf=self.confidence,
            iou=self.iou_threshold,
            imgsz=self.img_size,
            classes=classes,
            verbose=False,
        )

        detections: List[Detection] = []
        w, h = image.size

        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                cls_name = self.model.names[cls_id]

                crop = image.crop((int(x1), int(y1), int(x2), int(y2)))

                detections.append(Detection(
                    bbox=[x1 / w, y1 / h, x2 / w, y2 / h],
                    confidence=conf,
                    class_id=cls_id,
                    class_name=cls_name,
                    crop=crop,
                ))

        logger.debug(f"Detected {len(detections)} objects")
        return detections

    def detect_batch(self, images: List[Image.Image]) -> List[List[Detection]]:
        """Run detection on a batch of images."""
        return [self.detect(img) for img in images]

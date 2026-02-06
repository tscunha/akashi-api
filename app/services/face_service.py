"""
Face Recognition Service for detecting and identifying faces in videos/images.

Uses InsightFace or DeepFace for face detection and embedding generation.
"""

import base64
import io
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)


class FaceDetection:
    """A detected face with bounding box and embedding."""

    def __init__(
        self,
        bbox: tuple[float, float, float, float],  # x, y, w, h normalized
        embedding: list[float],
        confidence: float,
        timecode_ms: int | None = None,
        thumbnail: bytes | None = None,
    ):
        self.bbox = bbox
        self.embedding = embedding
        self.confidence = confidence
        self.timecode_ms = timecode_ms
        self.thumbnail = thumbnail

    def to_dict(self) -> dict[str, Any]:
        return {
            "bbox": {
                "x": self.bbox[0],
                "y": self.bbox[1],
                "w": self.bbox[2],
                "h": self.bbox[3],
            },
            "confidence": self.confidence,
            "timecode_ms": self.timecode_ms,
        }


class FaceService:
    """Service for face detection and recognition."""

    def __init__(self):
        self.model_name = getattr(settings, "face_model", "buffalo_l")
        self.min_confidence = getattr(settings, "face_min_confidence", 0.5)
        self.sample_interval = getattr(settings, "face_sample_interval", 1.0)  # seconds
        self._model = None

        logger.info(f"FaceService initialized: model={self.model_name}")

    def _get_model(self):
        """Lazy load the face analysis model."""
        if self._model is not None:
            return self._model

        try:
            from insightface.app import FaceAnalysis

            self._model = FaceAnalysis(
                name=self.model_name,
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            self._model.prepare(ctx_id=0, det_size=(640, 640))
            logger.info("InsightFace model loaded")
            return self._model

        except ImportError:
            logger.warning("InsightFace not available, trying DeepFace")

            try:
                from deepface import DeepFace
                self._model = "deepface"
                return self._model
            except ImportError:
                logger.error("No face recognition library available")
                raise ImportError(
                    "Install insightface or deepface: pip install insightface onnxruntime"
                )

    async def detect_faces_in_image(
        self,
        image_path: str | Path,
    ) -> list[FaceDetection]:
        """
        Detect faces in a single image.

        Args:
            image_path: Path to image file

        Returns:
            List of FaceDetection objects
        """
        import cv2

        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"Could not load image: {image_path}")

        return await self._detect_faces_in_frame(image)

    async def detect_faces_in_video(
        self,
        video_path: str | Path,
        sample_interval: float | None = None,
    ) -> list[FaceDetection]:
        """
        Detect faces in a video at regular intervals.

        Args:
            video_path: Path to video file
            sample_interval: Seconds between samples (default: 1.0)

        Returns:
            List of FaceDetection objects with timecodes
        """
        import cv2

        video_path = Path(video_path)
        sample_interval = sample_interval or self.sample_interval

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_interval = int(fps * sample_interval)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        all_faces = []
        frame_count = 0

        logger.info(
            f"Processing video: {video_path.name}, "
            f"fps={fps}, frames={total_frames}, interval={frame_interval}"
        )

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_count % frame_interval == 0:
                timecode_ms = int((frame_count / fps) * 1000)
                faces = await self._detect_faces_in_frame(frame, timecode_ms)
                all_faces.extend(faces)

                if faces:
                    logger.debug(
                        f"Frame {frame_count}: detected {len(faces)} faces at {timecode_ms}ms"
                    )

            frame_count += 1

        cap.release()

        logger.info(f"Video processing complete: {len(all_faces)} faces detected")
        return all_faces

    async def _detect_faces_in_frame(
        self,
        frame: np.ndarray,
        timecode_ms: int | None = None,
    ) -> list[FaceDetection]:
        """Detect faces in a single frame."""
        import cv2

        model = self._get_model()
        height, width = frame.shape[:2]
        faces = []

        if model == "deepface":
            # Use DeepFace
            try:
                from deepface import DeepFace

                results = DeepFace.represent(
                    frame,
                    model_name="Facenet512",
                    detector_backend="retinaface",
                    enforce_detection=False,
                )

                for result in results:
                    if "facial_area" in result:
                        area = result["facial_area"]
                        bbox = (
                            area["x"] / width,
                            area["y"] / height,
                            area["w"] / width,
                            area["h"] / height,
                        )

                        # Extract face thumbnail
                        x, y, w, h = area["x"], area["y"], area["w"], area["h"]
                        face_img = frame[y:y+h, x:x+w]
                        _, thumb_bytes = cv2.imencode(".jpg", face_img)

                        faces.append(FaceDetection(
                            bbox=bbox,
                            embedding=result.get("embedding", []),
                            confidence=result.get("face_confidence", 0.9),
                            timecode_ms=timecode_ms,
                            thumbnail=thumb_bytes.tobytes(),
                        ))

            except Exception as e:
                logger.debug(f"DeepFace detection failed: {e}")

        else:
            # Use InsightFace
            results = model.get(frame)

            for face in results:
                if face.det_score < self.min_confidence:
                    continue

                # Normalize bbox
                x1, y1, x2, y2 = face.bbox
                bbox = (
                    x1 / width,
                    y1 / height,
                    (x2 - x1) / width,
                    (y2 - y1) / height,
                )

                # Extract face thumbnail
                x1, y1, x2, y2 = map(int, face.bbox)
                face_img = frame[y1:y2, x1:x2]
                _, thumb_bytes = cv2.imencode(".jpg", face_img)

                faces.append(FaceDetection(
                    bbox=bbox,
                    embedding=face.embedding.tolist(),
                    confidence=float(face.det_score),
                    timecode_ms=timecode_ms,
                    thumbnail=thumb_bytes.tobytes(),
                ))

        return faces

    async def get_embedding_from_image(
        self,
        image_data: bytes | str,
    ) -> list[float]:
        """
        Get face embedding from an image.

        Args:
            image_data: Image bytes or base64 string

        Returns:
            Face embedding vector (512 dimensions)
        """
        import cv2
        import numpy as np

        # Decode base64 if needed
        if isinstance(image_data, str):
            image_data = base64.b64decode(image_data)

        # Load image
        nparr = np.frombuffer(image_data, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if image is None:
            raise ValueError("Could not decode image")

        # Detect faces
        faces = await self._detect_faces_in_frame(image)

        if not faces:
            raise ValueError("No face detected in image")

        # Return first face embedding
        return faces[0].embedding

    def compute_similarity(
        self,
        embedding1: list[float],
        embedding2: list[float],
    ) -> float:
        """
        Compute cosine similarity between two face embeddings.

        Args:
            embedding1: First embedding
            embedding2: Second embedding

        Returns:
            Similarity score (0-1, higher is more similar)
        """
        import numpy as np

        a = np.array(embedding1)
        b = np.array(embedding2)

        # Cosine similarity
        similarity = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

        # Convert from [-1, 1] to [0, 1]
        return float((similarity + 1) / 2)

    async def extract_frames(
        self,
        video_path: str | Path,
        interval_seconds: float = 10.0,
    ) -> list[tuple[int, bytes]]:
        """
        Extract frames from video at regular intervals.

        Args:
            video_path: Path to video file
            interval_seconds: Seconds between frames

        Returns:
            List of (timecode_ms, jpeg_bytes) tuples
        """
        import cv2

        video_path = Path(video_path)
        cap = cv2.VideoCapture(str(video_path))

        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_interval = int(fps * interval_seconds)

        frames = []
        frame_count = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_count % frame_interval == 0:
                timecode_ms = int((frame_count / fps) * 1000)
                _, jpg_bytes = cv2.imencode(".jpg", frame)
                frames.append((timecode_ms, jpg_bytes.tobytes()))

            frame_count += 1

        cap.release()
        return frames


# Singleton instance
face_service = FaceService()

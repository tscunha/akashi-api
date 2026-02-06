"""
Vision AI Service for scene description and analysis.

Uses GPT-4 Vision or local models (LLaVA) for image/video understanding.
"""

import base64
import io
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from app.core.config import settings

logger = logging.getLogger(__name__)


class SceneAnalysis:
    """Result of analyzing a scene/frame."""

    def __init__(
        self,
        description: str,
        objects: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        emotions: list[dict[str, Any]],
        text_ocr: str | None = None,
        timecode_start_ms: int = 0,
        timecode_end_ms: int = 0,
    ):
        self.description = description
        self.objects = objects  # [{object, confidence, bbox}]
        self.actions = actions  # [{action, confidence}]
        self.emotions = emotions  # [{emotion, confidence}]
        self.text_ocr = text_ocr
        self.timecode_start_ms = timecode_start_ms
        self.timecode_end_ms = timecode_end_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "objects": self.objects,
            "actions": self.actions,
            "emotions": self.emotions,
            "text_ocr": self.text_ocr,
            "timecode_start_ms": self.timecode_start_ms,
            "timecode_end_ms": self.timecode_end_ms,
        }


class VisionService:
    """Service for visual understanding using AI."""

    def __init__(self):
        self.mode = getattr(settings, "vision_mode", "api")  # api or local
        self.model = getattr(settings, "vision_model", "gpt-4-vision-preview")
        self.openai_api_key = getattr(settings, "openai_api_key", None)
        self.sample_interval = getattr(settings, "vision_sample_interval", 10)  # seconds

        logger.info(f"VisionService initialized: mode={self.mode}, model={self.model}")

    async def analyze_image(
        self,
        image_data: bytes | str,
        prompt: str | None = None,
    ) -> SceneAnalysis:
        """
        Analyze a single image.

        Args:
            image_data: Image bytes or base64 string
            prompt: Custom analysis prompt

        Returns:
            SceneAnalysis with description and detections
        """
        if isinstance(image_data, bytes):
            image_base64 = base64.b64encode(image_data).decode()
        else:
            image_base64 = image_data

        if self.mode == "api":
            return await self._analyze_with_openai(image_base64, prompt)
        else:
            return await self._analyze_with_local(image_base64, prompt)

    async def analyze_video(
        self,
        video_path: str | Path,
        interval_seconds: int | None = None,
    ) -> list[SceneAnalysis]:
        """
        Analyze a video by sampling frames at regular intervals.

        Args:
            video_path: Path to video file
            interval_seconds: Seconds between frame samples

        Returns:
            List of SceneAnalysis for each sampled frame
        """
        from app.services.face_service import face_service

        video_path = Path(video_path)
        interval_seconds = interval_seconds or self.sample_interval

        # Extract frames
        frames = await face_service.extract_frames(video_path, interval_seconds)

        logger.info(f"Analyzing {len(frames)} frames from {video_path.name}")

        analyses = []
        for i, (timecode_ms, frame_bytes) in enumerate(frames):
            try:
                analysis = await self.analyze_image(frame_bytes)
                analysis.timecode_start_ms = timecode_ms
                analysis.timecode_end_ms = timecode_ms + (interval_seconds * 1000)
                analyses.append(analysis)

                logger.debug(f"Frame {i+1}/{len(frames)} analyzed: {analysis.description[:50]}...")

            except Exception as e:
                logger.warning(f"Failed to analyze frame at {timecode_ms}ms: {e}")

        return analyses

    async def _analyze_with_openai(
        self,
        image_base64: str,
        prompt: str | None = None,
    ) -> SceneAnalysis:
        """Analyze image using OpenAI GPT-4 Vision API."""
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for Vision API")

        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package required: pip install openai")

        client = OpenAI(api_key=self.openai_api_key)

        system_prompt = """You are a video content analyzer. Analyze the image and provide:
1. A detailed description of the scene (1-2 sentences)
2. Main objects visible (with confidence 0-1)
3. Actions happening (with confidence 0-1)
4. Emotions of people if visible (with confidence 0-1)
5. Any text visible in the image (OCR)

Respond in JSON format:
{
    "description": "...",
    "objects": [{"object": "...", "confidence": 0.9}],
    "actions": [{"action": "...", "confidence": 0.8}],
    "emotions": [{"emotion": "...", "confidence": 0.7}],
    "text_ocr": "..."
}"""

        user_prompt = prompt or "Analyze this image in detail."

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            max_tokens=1000,
            response_format={"type": "json_object"},
        )

        # Parse response
        import json
        content = response.choices[0].message.content
        data = json.loads(content)

        return SceneAnalysis(
            description=data.get("description", ""),
            objects=data.get("objects", []),
            actions=data.get("actions", []),
            emotions=data.get("emotions", []),
            text_ocr=data.get("text_ocr"),
        )

    async def _analyze_with_local(
        self,
        image_base64: str,
        prompt: str | None = None,
    ) -> SceneAnalysis:
        """Analyze image using local model (LLaVA or similar)."""
        # This is a placeholder for local model integration
        # In production, integrate with LLaVA, Llama Vision, or similar

        logger.warning("Local vision model not implemented, using mock response")

        return SceneAnalysis(
            description="[Local model not available - mock response]",
            objects=[],
            actions=[],
            emotions=[],
            text_ocr=None,
        )

    async def generate_embedding(
        self,
        text: str,
    ) -> list[float]:
        """
        Generate text embedding for semantic search.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (1536 dimensions for ada-002)
        """
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for embeddings")

        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package required: pip install openai")

        client = OpenAI(api_key=self.openai_api_key)

        response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=text,
        )

        return response.data[0].embedding

    async def extract_keywords_from_description(
        self,
        description: str,
    ) -> list[dict[str, Any]]:
        """
        Extract keywords from a scene description using LLM.

        Args:
            description: Scene description text

        Returns:
            List of keywords with categories and confidence
        """
        if not self.openai_api_key:
            # Use simple extraction if no API key
            return self._simple_keyword_extraction(description)

        try:
            from openai import OpenAI
        except ImportError:
            return self._simple_keyword_extraction(description)

        client = OpenAI(api_key=self.openai_api_key)

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": """Extract keywords from the scene description.
Return JSON: {"keywords": [{"keyword": "...", "category": "object|action|emotion|location|person", "confidence": 0.9}]}"""
                },
                {"role": "user", "content": description},
            ],
            max_tokens=500,
            response_format={"type": "json_object"},
        )

        import json
        data = json.loads(response.choices[0].message.content)
        return data.get("keywords", [])

    def _simple_keyword_extraction(self, text: str) -> list[dict[str, Any]]:
        """Simple keyword extraction without LLM."""
        import re
        from collections import Counter

        # Tokenize and filter
        words = re.findall(r'\b[a-záàâãéêíóôõúç]{4,}\b', text.lower())

        # Common stop words
        stop_words = {
            "para", "como", "mais", "muito", "também", "onde", "quando",
            "esta", "este", "esse", "essa", "isso", "isto", "aqui",
            "the", "and", "for", "with", "from", "this", "that", "there",
        }

        filtered = [w for w in words if w not in stop_words]
        counts = Counter(filtered)

        return [
            {
                "keyword": word,
                "category": "topic",
                "confidence": min(count / 5, 1.0),
            }
            for word, count in counts.most_common(20)
        ]


# Singleton instance
vision_service = VisionService()

"""
Whisper Service for audio/video transcription.

Supports two modes:
- Local: Uses OpenAI Whisper installed locally (requires torch + whisper)
- API: Uses OpenAI Whisper API (requires OPENAI_API_KEY)
"""

import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from app.core.config import settings

logger = logging.getLogger(__name__)


class TranscriptionSegment:
    """A segment of transcribed text with timing."""

    def __init__(
        self,
        start_ms: int,
        end_ms: int,
        text: str,
        confidence: float | None = None,
    ):
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.text = text
        self.confidence = confidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "text": self.text,
            "confidence": self.confidence,
        }


class TranscriptionResult:
    """Result of a transcription."""

    def __init__(
        self,
        full_text: str,
        segments: list[TranscriptionSegment],
        language: str,
        duration_ms: int,
        model_version: str,
        processing_time_ms: int,
    ):
        self.full_text = full_text
        self.segments = segments
        self.language = language
        self.duration_ms = duration_ms
        self.model_version = model_version
        self.processing_time_ms = processing_time_ms

    @property
    def word_count(self) -> int:
        return len(self.full_text.split())

    @property
    def confidence_avg(self) -> float | None:
        confidences = [s.confidence for s in self.segments if s.confidence is not None]
        if not confidences:
            return None
        return sum(confidences) / len(confidences)

    def to_srt(self) -> str:
        """Generate SRT subtitle format."""
        lines = []
        for i, segment in enumerate(self.segments, 1):
            start_time = self._ms_to_srt_time(segment.start_ms)
            end_time = self._ms_to_srt_time(segment.end_ms)
            text = segment.text.strip()
            if not text:
                continue
            lines.append(str(i))
            lines.append(f"{start_time} --> {end_time}")
            lines.append(text)
            lines.append("")
        return "\n".join(lines)

    def to_vtt(self) -> str:
        """Generate WebVTT subtitle format."""
        lines = ["WEBVTT", ""]
        for segment in self.segments:
            start_time = self._ms_to_vtt_time(segment.start_ms)
            end_time = self._ms_to_vtt_time(segment.end_ms)
            text = segment.text.strip()
            if not text:
                continue
            lines.append(f"{start_time} --> {end_time}")
            lines.append(text)
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _ms_to_srt_time(ms: int) -> str:
        hours = ms // 3600000
        minutes = (ms % 3600000) // 60000
        seconds = (ms % 60000) // 1000
        milliseconds = ms % 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    @staticmethod
    def _ms_to_vtt_time(ms: int) -> str:
        hours = ms // 3600000
        minutes = (ms % 3600000) // 60000
        seconds = (ms % 60000) // 1000
        milliseconds = ms % 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


class WhisperService:
    """Service for transcribing audio/video files using Whisper."""

    def __init__(self):
        self.mode = getattr(settings, "whisper_mode", "local")  # local or api
        self.model = getattr(settings, "whisper_model", "base")  # tiny, base, small, medium, large-v3
        self.language = getattr(settings, "whisper_language", "pt")
        self.device = getattr(settings, "whisper_device", "cpu")  # cuda or cpu

        # For API mode
        self.openai_api_key = getattr(settings, "openai_api_key", None)

        logger.info(f"WhisperService initialized: mode={self.mode}, model={self.model}")

    async def transcribe_file(
        self,
        file_path: str | Path,
        language: str | None = None,
        model: str | None = None,
    ) -> TranscriptionResult:
        """
        Transcribe an audio/video file.

        Args:
            file_path: Path to the media file
            language: Override default language
            model: Override default model

        Returns:
            TranscriptionResult with full text and segments
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        language = language or self.language
        model = model or self.model

        start_time = time.time()

        if self.mode == "api":
            result = await self._transcribe_api(file_path, language)
        else:
            result = await self._transcribe_local(file_path, language, model)

        processing_time_ms = int((time.time() - start_time) * 1000)
        result.processing_time_ms = processing_time_ms

        logger.info(
            f"Transcription completed: {file_path.name}, "
            f"duration={result.duration_ms}ms, "
            f"words={result.word_count}, "
            f"processing={processing_time_ms}ms"
        )

        return result

    async def _transcribe_local(
        self,
        file_path: Path,
        language: str,
        model: str,
    ) -> TranscriptionResult:
        """Transcribe using local Whisper installation via CLI."""
        # Extract audio to temp file if needed
        audio_path = await self._extract_audio(file_path)

        try:
            # Run whisper CLI
            with tempfile.TemporaryDirectory() as temp_dir:
                output_dir = Path(temp_dir)

                cmd = [
                    "whisper",
                    str(audio_path),
                    "--model", model,
                    "--language", language,
                    "--output_format", "json",
                    "--output_dir", str(output_dir),
                    "--device", self.device,
                ]

                logger.info(f"Running Whisper: {' '.join(cmd)}")

                process = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=3600,  # 1 hour timeout
                )

                if process.returncode != 0:
                    logger.error(f"Whisper error: {process.stderr}")
                    raise RuntimeError(f"Whisper failed: {process.stderr}")

                # Parse JSON output
                json_file = output_dir / f"{audio_path.stem}.json"
                if not json_file.exists():
                    # Try finding any json file
                    json_files = list(output_dir.glob("*.json"))
                    if json_files:
                        json_file = json_files[0]
                    else:
                        raise RuntimeError("Whisper output not found")

                with open(json_file) as f:
                    data = json.load(f)

                return self._parse_whisper_output(data, language, model)

        finally:
            # Cleanup temp audio if created
            if audio_path != file_path and audio_path.exists():
                audio_path.unlink()

    async def _transcribe_api(
        self,
        file_path: Path,
        language: str,
    ) -> TranscriptionResult:
        """Transcribe using OpenAI Whisper API."""
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for API mode")

        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package is required for API mode. Install with: pip install openai")

        client = OpenAI(api_key=self.openai_api_key)

        # Extract audio if video
        audio_path = await self._extract_audio(file_path)

        try:
            with open(audio_path, "rb") as audio_file:
                # Use verbose_json to get timestamps
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )

            # Parse response
            segments = []
            for seg in response.segments or []:
                segments.append(TranscriptionSegment(
                    start_ms=int(seg.start * 1000),
                    end_ms=int(seg.end * 1000),
                    text=seg.text,
                    confidence=None,  # API doesn't provide confidence
                ))

            duration_ms = int(response.duration * 1000) if response.duration else 0

            return TranscriptionResult(
                full_text=response.text,
                segments=segments,
                language=language,
                duration_ms=duration_ms,
                model_version="whisper-1-api",
                processing_time_ms=0,  # Will be set by caller
            )

        finally:
            if audio_path != file_path and audio_path.exists():
                audio_path.unlink()

    async def _extract_audio(self, file_path: Path) -> Path:
        """Extract audio from video file if needed."""
        # Check if it's already audio
        audio_extensions = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma"}
        if file_path.suffix.lower() in audio_extensions:
            return file_path

        # Extract audio using ffmpeg
        temp_audio = Path(tempfile.gettempdir()) / f"{file_path.stem}_audio.wav"

        cmd = [
            "ffmpeg",
            "-i", str(file_path),
            "-vn",  # No video
            "-acodec", "pcm_s16le",
            "-ar", "16000",  # 16kHz for Whisper
            "-ac", "1",  # Mono
            "-y",  # Overwrite
            str(temp_audio),
        ]

        logger.info(f"Extracting audio: {file_path.name}")

        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )

        if process.returncode != 0:
            logger.error(f"FFmpeg error: {process.stderr}")
            raise RuntimeError(f"Audio extraction failed: {process.stderr}")

        return temp_audio

    def _parse_whisper_output(
        self,
        data: dict[str, Any],
        language: str,
        model: str,
    ) -> TranscriptionResult:
        """Parse Whisper JSON output."""
        segments = []

        for seg in data.get("segments", []):
            segments.append(TranscriptionSegment(
                start_ms=int(seg["start"] * 1000),
                end_ms=int(seg["end"] * 1000),
                text=seg["text"],
                confidence=seg.get("avg_logprob"),  # Log probability as confidence proxy
            ))

        full_text = data.get("text", "")
        if not full_text and segments:
            full_text = " ".join(s.text.strip() for s in segments)

        # Calculate duration from last segment
        duration_ms = 0
        if segments:
            duration_ms = segments[-1].end_ms

        return TranscriptionResult(
            full_text=full_text,
            segments=segments,
            language=data.get("language", language),
            duration_ms=duration_ms,
            model_version=model,
            processing_time_ms=0,  # Will be set by caller
        )


# Singleton instance
whisper_service = WhisperService()

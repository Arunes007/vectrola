"""Whisper-based audio transcription."""

from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from vectrola.config import get_config


@dataclass
class TranscriptionResult:
    """Result of audio transcription."""

    text: str
    segments: list[dict]  # [{"start": float, "end": float, "text": str}, ...]
    language: str
    language_probability: float


class Transcriber:
    """Transcribe audio files using faster-whisper."""

    def __init__(
        self,
        model_size: Optional[str] = None,
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
    ):
        """
        Initialize the transcriber.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
            device: Device to use (cpu, cuda, auto)
            compute_type: Compute type (int8, float16, float32)
        """
        config = get_config()
        self.model_size = model_size or config.whisper_model
        self.device = device or config.whisper_device
        self.compute_type = compute_type or config.whisper_compute_type

        self._model = None

    @property
    def model(self):
        """Lazy load the Whisper model."""
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def transcribe(
        self,
        audio_path: Path,
        beam_size: int = 5,
    ) -> TranscriptionResult:
        """
        Transcribe an audio file.

        Args:
            audio_path: Path to the audio file
            beam_size: Beam size for decoding

        Returns:
            TranscriptionResult with full text and timestamped segments
        """
        segments, info = self.model.transcribe(
            str(audio_path),
            beam_size=beam_size,
        )

        # Collect segments (generator -> list)
        segment_list = []
        text_parts = []

        for segment in segments:
            segment_list.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
            })
            text_parts.append(segment.text.strip())

        return TranscriptionResult(
            text=" ".join(text_parts),
            segments=segment_list,
            language=info.language,
            language_probability=info.language_probability,
        )


# Convenience function
def transcribe_audio(audio_path: Path) -> TranscriptionResult:
    """Transcribe an audio file using default settings."""
    transcriber = Transcriber()
    return transcriber.transcribe(audio_path)

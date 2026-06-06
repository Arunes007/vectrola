"""Demucs-based vocal separation for cleaner transcription."""

from pathlib import Path
from typing import Optional
import tempfile
import shutil

from vectrola.config import get_config


class StemSeparator:
    """
    Separate vocals from instrumentals using Demucs.

    This dramatically improves Whisper transcription accuracy for music
    by removing background instruments that confuse the speech model.
    """

    def __init__(self, model_name: str = "htdemucs"):
        """
        Initialize the separator.

        Args:
            model_name: Demucs model to use
                - "htdemucs": Default, good quality (4 stems: drums, bass, other, vocals)
                - "htdemucs_ft": Fine-tuned, better quality but slower
                - "mdx_extra": MDX architecture, different quality profile
        """
        self.model_name = model_name
        self._model = None
        self._cache_dir = get_config().cache_dir / "stems"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def model(self):
        """Lazy load the Demucs model."""
        if self._model is None:
            import torch
            from demucs.pretrained import get_model

            self._model = get_model(self.model_name)
            # Use CPU by default, GPU if available
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model.to(self.device)
        return self._model

    def separate(self, audio_path: Path, use_cache: bool = True) -> Path:
        """
        Separate vocals from an audio file.

        Args:
            audio_path: Path to the audio file
            use_cache: If True, check cache before processing

        Returns:
            Path to the isolated vocals audio file
        """
        import torch
        import torchaudio
        from demucs.apply import apply_model

        audio_path = Path(audio_path)

        # Check cache first
        cache_key = f"{audio_path.stem}_{audio_path.stat().st_mtime_ns}"
        cached_vocals = self._cache_dir / f"{cache_key}_vocals.wav"

        if use_cache and cached_vocals.exists():
            return cached_vocals

        # Load audio
        waveform, sample_rate = torchaudio.load(str(audio_path))

        # Resample to model's sample rate if needed (44100 Hz for Demucs)
        if sample_rate != self.model.samplerate:
            resampler = torchaudio.transforms.Resample(sample_rate, self.model.samplerate)
            waveform = resampler(waveform)

        # Ensure stereo (Demucs expects 2 channels)
        if waveform.shape[0] == 1:
            waveform = waveform.repeat(2, 1)
        elif waveform.shape[0] > 2:
            waveform = waveform[:2]

        # Add batch dimension: (channels, samples) -> (1, channels, samples)
        waveform = waveform.unsqueeze(0).to(self.device)

        # Apply model
        with torch.no_grad():
            sources = apply_model(self.model, waveform, device=self.device)

        # sources shape: (1, num_sources, channels, samples)
        # For htdemucs: sources are [drums, bass, other, vocals]
        # Vocals is the last source (index 3)
        vocals_idx = self.model.sources.index("vocals")
        vocals = sources[0, vocals_idx]  # (channels, samples)

        # Save vocals to cache
        torchaudio.save(str(cached_vocals), vocals.cpu(), self.model.samplerate)

        return cached_vocals

    def clear_cache(self):
        """Clear the stems cache."""
        if self._cache_dir.exists():
            shutil.rmtree(self._cache_dir)
            self._cache_dir.mkdir(parents=True, exist_ok=True)


# Convenience function
def separate_vocals(audio_path: Path) -> Path:
    """
    Separate vocals from an audio file using default settings.

    Returns path to isolated vocals WAV file.
    """
    separator = StemSeparator()
    return separator.separate(audio_path)

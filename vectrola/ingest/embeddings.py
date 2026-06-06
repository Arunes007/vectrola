"""Text and audio embeddings for vector search."""

from typing import Optional
import numpy as np

from vectrola.config import get_config


# Mood synonyms for better semantic matching
# When we store "melancholic", we also store synonyms so "sad" queries match
MOOD_SYNONYMS = {
    "melancholic": ["sad", "sorrowful", "gloomy", "depressed", "heartbroken"],
    "hopeless": ["desperate", "despair", "defeated", "bleak", "desolate"],
    "hopeful": ["optimistic", "uplifting", "encouraging", "positive"],
    "romantic": ["loving", "passionate", "tender", "affectionate"],
    "energetic": ["upbeat", "lively", "vibrant", "dynamic", "exciting"],
    "aggressive": ["angry", "intense", "fierce", "violent", "rage"],
    "peaceful": ["calm", "serene", "tranquil", "relaxing", "soothing"],
    "nostalgic": ["reminiscent", "wistful", "longing for past", "sentimental"],
    "introspective": ["reflective", "thoughtful", "contemplative", "meditative"],
    "euphoric": ["ecstatic", "joyful", "elated", "blissful", "happy"],
    "sad": ["melancholic", "sorrowful", "depressed", "heartbroken", "gloomy"],
    "happy": ["joyful", "cheerful", "euphoric", "elated", "upbeat"],
    "angry": ["aggressive", "furious", "rage", "intense", "fierce"],
}


def build_searchable_text(lyrics: str, moods: list, themes: list, narrative: str) -> str:
    """
    Build searchable text with weighted moods/themes.

    Strategy:
    1. Include lyrics (full semantic content)
    2. Repeat moods 3x with synonyms for stronger signal
    3. Repeat themes 2x
    4. Include narrative

    This gives moods/themes more weight in the embedding so
    searches like "sad hopeless song" match better.
    """
    parts = []

    # 1. Lyrics (base content)
    if lyrics:
        parts.append(lyrics)

    # 2. Moods - repeated 3x with synonyms for stronger matching
    if moods:
        mood_text = ", ".join(moods)
        # Add synonyms
        expanded_moods = list(moods)
        for mood in moods:
            mood_lower = mood.lower()
            if mood_lower in MOOD_SYNONYMS:
                expanded_moods.extend(MOOD_SYNONYMS[mood_lower])

        expanded_text = ", ".join(expanded_moods)
        # Repeat for weight
        parts.append(f"Mood: {expanded_text}")
        parts.append(f"Feeling: {expanded_text}")
        parts.append(f"Emotion: {mood_text}")

    # 3. Themes - repeated 2x
    if themes:
        theme_text = ", ".join(themes)
        parts.append(f"Themes: {theme_text}")
        parts.append(f"About: {theme_text}")

    # 4. Narrative
    if narrative:
        parts.append(f"Story: {narrative}")

    return "\n".join(parts)


class TextEmbedder:
    """
    Generate text embeddings using sentence-transformers.

    Uses paraphrase-multilingual-MiniLM-L12-v2 (384 dimensions) for Hindi+English support.
    This model understands both Hindi lyrics and English search queries.
    """

    # Multilingual model for Hindi + English
    MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
    VECTOR_SIZE = 384

    def __init__(self):
        self._model = None

    @property
    def model(self):
        """Lazy load the sentence-transformers model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.MODEL_NAME)
        return self._model

    def embed(self, text: str) -> list[float]:
        """
        Embed a single text string.

        Args:
            text: Text to embed (lyrics, query, etc.)

        Returns:
            384-dimensional embedding vector
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            return [0.0] * self.VECTOR_SIZE

        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embed multiple texts efficiently.

        Args:
            texts: List of texts to embed

        Returns:
            List of 384-dimensional embedding vectors
        """
        if not texts:
            return []

        # Filter empty texts but track indices
        valid_texts = []
        valid_indices = []
        for i, text in enumerate(texts):
            if text and text.strip():
                valid_texts.append(text)
                valid_indices.append(i)

        if not valid_texts:
            return [[0.0] * self.VECTOR_SIZE for _ in texts]

        # Batch encode
        embeddings = self.model.encode(valid_texts, convert_to_numpy=True)

        # Reconstruct full list with zero vectors for empty texts
        result = [[0.0] * self.VECTOR_SIZE for _ in texts]
        for i, idx in enumerate(valid_indices):
            result[idx] = embeddings[i].tolist()

        return result


# Singleton instance
_text_embedder: Optional[TextEmbedder] = None


def get_text_embedder() -> TextEmbedder:
    """Get the singleton TextEmbedder instance."""
    global _text_embedder
    if _text_embedder is None:
        _text_embedder = TextEmbedder()
    return _text_embedder


def embed_text(text: str) -> list[float]:
    """Convenience function to embed a single text."""
    return get_text_embedder().embed(text)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Convenience function to embed multiple texts."""
    return get_text_embedder().embed_batch(texts)


class AudioEmbedder:
    """
    Generate audio embeddings using CLAP (Contrastive Language-Audio Pretraining).

    CLAP produces 512-dim embeddings that are aligned with text embeddings,
    meaning you can search for "dark ambient texture" and find matching audio.
    """

    MODEL_NAME = "laion/clap-htsat-unfused"  # Smaller, faster model
    VECTOR_SIZE = 512

    def __init__(self):
        self._model = None
        self._processor = None

    @property
    def model(self):
        """Lazy load CLAP model."""
        if self._model is None:
            from transformers import ClapModel, ClapProcessor
            self._model = ClapModel.from_pretrained(self.MODEL_NAME)
            self._processor = ClapProcessor.from_pretrained(self.MODEL_NAME)
        return self._model

    @property
    def processor(self):
        """Get CLAP processor."""
        if self._processor is None:
            from transformers import ClapProcessor
            self._processor = ClapProcessor.from_pretrained(self.MODEL_NAME)
        return self._processor

    def embed_audio(self, audio_path: str, duration: float = 10.0, offset: float = 30.0) -> list[float]:
        """
        Generate audio embedding from a file.

        Args:
            audio_path: Path to audio file
            duration: Seconds to load (default 10s for speed)
            offset: Start offset in seconds (skip intro)

        Returns:
            512-dim CLAP embedding
        """
        import librosa

        # Load audio segment
        y, sr = librosa.load(audio_path, sr=48000, duration=duration, offset=offset)

        # Process with CLAP
        inputs = self.processor(audios=y, sampling_rate=sr, return_tensors="pt")
        audio_embed = self.model.get_audio_features(**inputs)

        return audio_embed[0].detach().numpy().tolist()

    def embed_text(self, text: str) -> list[float]:
        """
        Generate CLAP embedding from text description.

        This is the magic of CLAP - text descriptions like "dark ambient drone"
        produce embeddings in the same space as audio, enabling cross-modal search.

        Args:
            text: Audio description (e.g., "slow piano with rain sounds")

        Returns:
            512-dim CLAP embedding aligned with audio space
        """
        text_inputs = self.processor(text=[text], return_tensors="pt", padding=True)
        text_embed = self.model.get_text_features(**text_inputs)

        return text_embed[0].detach().numpy().tolist()


# Singleton instances
_audio_embedder: Optional[AudioEmbedder] = None


def get_audio_embedder() -> AudioEmbedder:
    """Get the singleton AudioEmbedder instance."""
    global _audio_embedder
    if _audio_embedder is None:
        _audio_embedder = AudioEmbedder()
    return _audio_embedder


def embed_audio(audio_path: str, duration: float = 10.0, offset: float = 30.0) -> list[float]:
    """Convenience function to embed audio from a file."""
    return get_audio_embedder().embed_audio(audio_path, duration, offset)

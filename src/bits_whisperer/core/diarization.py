"""Cloud-free local speaker diarization using pyannote.audio.

Provides speaker identification as a post-processing step that can be
applied to the output of ANY transcription provider. This enables
diarization even for providers that don't natively support it (e.g.
local Whisper, Groq, OpenAI).

Requirements:
    pip install pyannote.audio torch torchaudio

The ``pyannote/speaker-diarization-3.1`` model requires a HuggingFace
auth token. Obtain one from https://huggingface.co/settings/tokens
and accept the model licence at
https://huggingface.co/pyannote/speaker-diarization-3.1

Usage::

    diarizer = LocalDiarizer(hf_token="hf_...")
    turns = diarizer.diarize("audio.wav", min_speakers=2, max_speakers=6)
    result = diarizer.apply_to_transcript(result, turns)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from bits_whisperer.core.job import TranscriptionResult

logger = logging.getLogger(__name__)

# Default pyannote model
DEFAULT_MODEL = "pyannote/speaker-diarization-3.1"


@dataclass
class SpeakerTurn:
    """A single speaker turn from diarization output."""

    start: float
    end: float
    speaker_id: str


def is_available() -> bool:
    """Check whether pyannote.audio is installed and usable.

    Returns:
        True if the pyannote.audio pipeline can be imported.
    """
    try:
        import pyannote.audio  # noqa: F401

        return True
    except ImportError:
        return False


class LocalDiarizer:
    """Local speaker diarization using the pyannote.audio pipeline.

    Runs entirely on-device -- no cloud calls. Requires PyTorch and
    pyannote.audio with a HuggingFace auth token for gated models.
    """

    def __init__(
        self,
        hf_token: str = "",
        model: str = DEFAULT_MODEL,
    ) -> None:
        """Initialise the diarizer.

        Args:
            hf_token: HuggingFace auth token for gated models.
            model: pyannote model identifier.
        """
        self._hf_token = hf_token
        self._model_id = model
        self._pipeline = None

    def _load_pipeline(self) -> None:
        """Lazy-load the pyannote pipeline on first use."""
        if self._pipeline is not None:
            return
        try:
            from pyannote.audio import Pipeline
        except ImportError:
            raise RuntimeError(
                "pyannote.audio is not installed. Install it with:\n"
                "  pip install pyannote.audio torch torchaudio\n\n"
                "Then accept the model licence at:\n"
                "  https://huggingface.co/pyannote/speaker-diarization-3.1"
            ) from None

        logger.info("Loading pyannote pipeline: %s", self._model_id)
        kwargs = {}
        if self._hf_token:
            kwargs["use_auth_token"] = self._hf_token
        self._pipeline = Pipeline.from_pretrained(self._model_id, **kwargs)
        logger.info("pyannote pipeline loaded successfully")

    def diarize(
        self,
        audio_path: str,
        min_speakers: int = 1,
        max_speakers: int = 10,
    ) -> list[SpeakerTurn]:
        """Run speaker diarization on an audio file.

        Args:
            audio_path: Path to the audio file (WAV preferred).
            min_speakers: Minimum expected number of speakers.
            max_speakers: Maximum expected number of speakers.

        Returns:
            List of SpeakerTurn with start/end times and speaker IDs.

        Raises:
            RuntimeError: If pyannote.audio is not available.
        """
        self._load_pipeline()

        logger.info(
            "Diarizing %s (speakers: %d-%d)",
            audio_path,
            min_speakers,
            max_speakers,
        )

        params = {}
        if min_speakers > 1:
            params["min_speakers"] = min_speakers
        if max_speakers < 10:
            params["max_speakers"] = max_speakers

        diarization = self._pipeline(audio_path, **params)

        turns: list[SpeakerTurn] = []
        speaker_counter = 0
        speaker_label_map: dict[str, str] = {}

        for turn, _, speaker_label in diarization.itertracks(yield_label=True):
            # Map internal labels (SPEAKER_00, SPEAKER_01, ...) to
            # user-friendly names (Speaker 1, Speaker 2, ...)
            if speaker_label not in speaker_label_map:
                speaker_counter += 1
                speaker_label_map[speaker_label] = f"Speaker {speaker_counter}"

            turns.append(
                SpeakerTurn(
                    start=turn.start,
                    end=turn.end,
                    speaker_id=speaker_label_map[speaker_label],
                )
            )

        logger.info(
            "Diarization complete: %d turns, %d speakers",
            len(turns),
            speaker_counter,
        )
        return turns

    def apply_to_transcript(
        self,
        result: TranscriptionResult,
        turns: list[SpeakerTurn],
    ) -> TranscriptionResult:
        """Merge diarization speaker turns into transcription segments.

        For each transcription segment, finds the speaker turn with the
        most temporal overlap and assigns that speaker. This works with
        output from any transcription provider.

        Args:
            result: TranscriptionResult with segments (timestamps required).
            turns: Speaker turns from ``diarize()``.

        Returns:
            Updated TranscriptionResult with speaker labels assigned.
        """
        if not turns or not result.segments:
            return result

        for seg in result.segments:
            best_speaker = ""
            best_overlap = 0.0

            for turn in turns:
                # Calculate temporal overlap
                overlap_start = max(seg.start, turn.start)
                overlap_end = min(seg.end, turn.end)
                overlap = max(0.0, overlap_end - overlap_start)

                if overlap > best_overlap:
                    best_overlap = overlap
                    best_speaker = turn.speaker_id

            if best_speaker:
                seg.speaker = best_speaker

        # Collect unique speakers into the speaker_map
        seen: dict[str, str] = {}
        for seg in result.segments:
            if seg.speaker and seg.speaker not in seen:
                seen[seg.speaker] = seg.speaker  # Identity map initially
        result.speaker_map = seen

        return result


def apply_speaker_map(
    result: TranscriptionResult,
    speaker_map: dict[str, str],
) -> TranscriptionResult:
    """Rename speakers in a transcript using a speaker map.

    This applies user-defined speaker names (e.g. "Speaker 1" -> "Alice")
    to all segments. Used for post-transcription speaker correction.

    Args:
        result: TranscriptionResult with speaker labels.
        speaker_map: Dict mapping original speaker IDs to display names.

    Returns:
        Updated TranscriptionResult with renamed speakers.
    """
    if not speaker_map:
        return result

    for seg in result.segments:
        if seg.speaker in speaker_map:
            seg.speaker = speaker_map[seg.speaker]

    # Update the result's own speaker map
    result.speaker_map = {v: v for v in speaker_map.values()}
    return result

"""VOICEVOX HTTP API integration for text-to-speech synthesis."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from typing import Optional

import requests


VOICEVOX_BASE_URL = "http://localhost:50021"

_VOWEL_OPENNESS: dict[str, float] = {
    "a": 1.0,
    "i": 0.6,
    "u": 0.5,
    "e": 0.7,
    "o": 0.8,
    "N": 0.3,
    "cl": 0.0,
}


@dataclass
class MoraInfo:
    """Mora (syllable) timing information from VOICEVOX."""

    text: str
    consonant: Optional[str]
    consonant_length: float
    vowel: str
    vowel_length: float
    pitch: float

    @property
    def duration(self) -> float:
        return self.consonant_length + self.vowel_length


@dataclass
class AccentPhrase:
    """Accent phrase containing mora information."""

    moras: list[MoraInfo]
    accent: int
    pause_mora: Optional[MoraInfo]


@dataclass
class AudioQuery:
    """Full audio query result from VOICEVOX."""

    accent_phrases: list[AccentPhrase]
    speed_scale: float
    pitch_scale: float
    intonation_scale: float
    volume_scale: float
    pre_phoneme_length: float
    post_phoneme_length: float
    output_sampling_rate: int
    output_stereo: bool
    kana: str


@dataclass
class LipSyncFrame:
    """A single mouth-shape keyframe for lip sync animation."""

    time: float
    mouth_open: float  # 0.0 (closed) to 1.0 (open)


class VoicevoxClient:
    """Client for the VOICEVOX HTTP API."""

    def __init__(self, base_url: str = VOICEVOX_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        """Check if VOICEVOX engine is running."""
        try:
            response = requests.get(f"{self.base_url}/version", timeout=2)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def get_speakers(self) -> list[dict]:
        """Return a list of available speakers."""
        response = requests.get(f"{self.base_url}/speakers", timeout=10)
        response.raise_for_status()
        return response.json()

    def create_audio_query(self, text: str, speaker_id: int) -> dict:
        """Create an audio query for the given text and speaker."""
        response = requests.post(
            f"{self.base_url}/audio_query",
            params={"text": text, "speaker": speaker_id},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def synthesize(self, audio_query: dict, speaker_id: int) -> bytes:
        """Synthesize audio from an audio query. Returns raw WAV bytes."""
        response = requests.post(
            f"{self.base_url}/synthesis",
            params={"speaker": speaker_id},
            headers={"Content-Type": "application/json"},
            data=json.dumps(audio_query),
            timeout=60,
        )
        response.raise_for_status()
        return response.content

    def synthesize_to_file(
        self, text: str, speaker_id: int, output_path: Optional[str] = None
    ) -> str:
        """
        Synthesize text to a WAV file.

        Returns the path to the output file. If output_path is not given,
        a temporary file is created.
        """
        audio_query = self.create_audio_query(text, speaker_id)
        wav_bytes = self.synthesize(audio_query, speaker_id)

        if output_path is None:
            fd, output_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)

        with open(output_path, "wb") as f:
            f.write(wav_bytes)

        return output_path

    def _lip_frames_for_mora(
        self, mora: dict, current_time: float, speed: float
    ) -> tuple[list[LipSyncFrame], float]:
        """Return lip-sync frames for a single mora and the updated elapsed time.

        Consonants produce a closed-mouth frame; vowels produce a frame whose
        openness is taken from ``_VOWEL_OPENNESS``.
        """
        frames: list[LipSyncFrame] = []
        consonant_len = mora.get("consonantLength") or 0.0
        vowel_len = mora.get("vowelLength", 0.0)
        vowel = mora.get("vowel", "a")

        if consonant_len > 0:
            frames.append(LipSyncFrame(time=current_time / speed, mouth_open=0.0))
            current_time += consonant_len

        openness = _VOWEL_OPENNESS.get(vowel, 0.5)
        frames.append(LipSyncFrame(time=current_time / speed, mouth_open=openness))
        current_time += vowel_len

        return frames, current_time

    def get_lip_sync_frames(
        self, audio_query: dict, fps: float = 30.0
    ) -> list[LipSyncFrame]:
        """Convert VOICEVOX mora data into lip-sync keyframes.

        Each mora contributes frames for its consonant (mouth closed) and vowel
        (mouth open proportional to the vowel).  Pauses between accent phrases
        produce additional closed-mouth frames.
        """
        frames: list[LipSyncFrame] = [LipSyncFrame(time=0.0, mouth_open=0.0)]
        current_time: float = audio_query.get("prePhonemeLength", 0.0)
        speed: float = audio_query.get("speedScale", 1.0)

        for phrase in audio_query.get("accentPhrases", []):
            for mora in phrase.get("moras", []):
                mora_frames, current_time = self._lip_frames_for_mora(
                    mora, current_time, speed
                )
                frames.extend(mora_frames)

            pause_mora = phrase.get("pauseMora")
            if pause_mora:
                frames.append(LipSyncFrame(time=current_time / speed, mouth_open=0.0))
                current_time += pause_mora.get("vowelLength", 0.0)

        frames.append(LipSyncFrame(time=current_time / speed, mouth_open=0.0))
        return frames

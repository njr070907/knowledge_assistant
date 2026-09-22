from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from functools import partial

import numpy as np

from .config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


class LocalTranscriber:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None
        self._load_error: str | None = None
        self._lock = asyncio.Lock()

    @property
    def status(self) -> dict[str, object]:
        return {
            "ready": self._model is not None,
            "model": self.settings.model_name,
            "device": self.settings.device,
            "computeType": self.settings.compute_type,
            "loadError": self._load_error,
        }

    def _load_model(self) -> None:
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.settings.model_name,
                device=self.settings.device,
                compute_type=self.settings.compute_type,
                cpu_threads=self.settings.cpu_threads,
                num_workers=1,
            )
            self._load_error = None
        except Exception as exc:  # model/runtime errors should be visible in the UI
            self._load_error = str(exc)
            raise

    def _transcribe_sync(self, pcm_bytes: bytes, offset: float) -> list[TranscriptSegment]:
        self._load_model()
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self._model.transcribe(
            audio,
            language=self.settings.language,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            beam_size=1,
            condition_on_previous_text=False,
            word_timestamps=False,
            initial_prompt="高等数学，线性代数，马克思主义基本原理，计算机体系结构，RISC-V，Verilog。",
        )
        result: list[TranscriptSegment] = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                result.append(TranscriptSegment(offset + segment.start, offset + segment.end, text))
        return result

    async def transcribe(self, pcm_bytes: bytes, offset: float) -> list[TranscriptSegment]:
        async with self._lock:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, partial(self._transcribe_sync, pcm_bytes, offset))


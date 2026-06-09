import logging
import threading
from dataclasses import dataclass, field

from faster_whisper import WhisperModel

from .config import Settings

logger = logging.getLogger("transcriber")


@dataclass
class Segment:
    id: int
    start: float
    end: float
    text: str
    words: list[dict] | None = None


@dataclass
class TranscriptionResult:
    text: str
    language: str
    language_probability: float
    duration: float
    segments: list[Segment] = field(default_factory=list)


class Transcriber:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._lock = threading.Lock()
        logger.info(
            "Loading whisper model '%s' (device=%s, compute=%s)…",
            settings.whisper_model,
            settings.whisper_device,
            settings.whisper_compute_type,
        )
        self._model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            cpu_threads=settings.whisper_cpu_threads,
            num_workers=settings.whisper_num_workers,
            download_root=settings.whisper_download_root,
        )
        logger.info("Model loaded.")

    @property
    def model_name(self) -> str:
        return self._settings.whisper_model

    def transcribe(
        self,
        audio_path: str,
        *,
        language: str | None = None,
        beam_size: int | None = None,
        vad_filter: bool | None = None,
        word_timestamps: bool | None = None,
        initial_prompt: str | None = None,
    ) -> TranscriptionResult:
        s = self._settings
        language = language or s.whisper_language
        beam_size = beam_size if beam_size is not None else s.whisper_beam_size
        vad_filter = vad_filter if vad_filter is not None else s.whisper_vad_filter
        word_timestamps = (
            word_timestamps if word_timestamps is not None else s.whisper_word_timestamps
        )
        initial_prompt = (
            initial_prompt if initial_prompt is not None else s.whisper_initial_prompt
        ) or None

        with self._lock:
            segments_iter, info = self._model.transcribe(
                audio_path,
                language=language,
                beam_size=beam_size,
                vad_filter=vad_filter,
                word_timestamps=word_timestamps,
                initial_prompt=initial_prompt,
                condition_on_previous_text=s.whisper_condition_on_previous_text,
            )

            segments: list[Segment] = []
            parts: list[str] = []

            total = info.duration or 0.0
            next_pct = 10
            for seg in segments_iter:
                words = None
                if word_timestamps and seg.words:
                    words = [
                        {"start": w.start, "end": w.end, "word": w.word}
                        for w in seg.words
                    ]
                segments.append(
                    Segment(
                        id=seg.id,
                        start=seg.start,
                        end=seg.end,
                        text=seg.text.strip(),
                        words=words,
                    )
                )
                parts.append(seg.text)

                if total:
                    pct = seg.end / total * 100
                    if pct >= next_pct:
                        logger.info("progress %d%% (%.0f/%.0fs of audio)",
                                    int(pct), seg.end, total)
                        next_pct = int(pct // 10) * 10 + 10

        return TranscriptionResult(
            text="".join(parts).strip(),
            language=info.language,
            language_probability=info.language_probability,
            duration=info.duration,
            segments=segments,
        )

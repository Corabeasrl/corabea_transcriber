import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from .audio import AudioError, concat_to_wav, make_workdir
from .config import Settings
from .s3 import S3Store
from .summarizer import Summarizer
from .transcriber import Transcriber

logger = logging.getLogger("pipeline")


class Status(str, Enum):
    DONE = "done"
    SKIPPED = "skipped"
    SUMMARIZED = "summarized"
    NO_AUDIO = "no_audio"
    DEFERRED = "deferred"


class PipelineResult:
    def __init__(self, status: Status, roomhash: str, manifest: str | None = None,
                 transcript_key: str | None = None, num_fragments: int = 0):
        self.status = status
        self.roomhash = roomhash
        self.manifest = manifest
        self.transcript_key = transcript_key
        self.num_fragments = num_fragments

    def __repr__(self) -> str:
        return (f"PipelineResult(status={self.status.value}, roomhash={self.roomhash}, "
                f"manifest={self.manifest}, fragments={self.num_fragments})")


class Pipeline:
    """Transcribe one room's recordings and write the result to S3."""

    def __init__(self, settings: Settings, store: S3Store, transcriber: Transcriber,
                 summarizer: Summarizer | None = None):
        self._s = settings
        self._store = store
        self._transcriber = transcriber
        self._summarizer = summarizer or Summarizer(settings)
    
    def _summarize(self, roomhash: str, manifest: str, text: str) -> None:
        try:
            summary = self._summarizer.summarize(text)
            key = self._store.transcript_key(roomhash, manifest, "summary.txt")
            self._store.put_text(key, summary, "text/plain; charset=utf-8")
            logger.info("[%s] summary -> %s", roomhash, key)
        except Exception as e:
            logger.warning("[%s] summary skipped (best-effort): %s", roomhash, e)

    def process_room(self, roomhash: str, force: bool = False) -> PipelineResult:
        objs = self._store.list_recordings(roomhash)
        if not objs:
            logger.info("[%s] no WAV fragments found", roomhash)
            return PipelineResult(Status.NO_AUDIO, roomhash)

        manifest = self._store.manifest_hash(objs)

        if not force and self._store.transcript_exists(roomhash, manifest):
            if self._summarizer.enabled and not self._store.summary_exists(roomhash, manifest):
                text = self._store.get_text(self._store.transcript_key(roomhash, manifest, "txt"))
                self._summarize(roomhash, manifest, text)
                return PipelineResult(Status.SUMMARIZED, roomhash, manifest,
                                      num_fragments=len(objs))
            logger.info("[%s] transcript %s already exists, skipping", roomhash, manifest)
            return PipelineResult(Status.SKIPPED, roomhash, manifest,
                                  num_fragments=len(objs))

        age = self._store.newest_age_seconds(objs)
        if age < self._s.min_object_age_seconds:
            logger.info("[%s] newest fragment is %.0fs old (< %ds), deferring",
                        roomhash, age, self._s.min_object_age_seconds)
            return PipelineResult(Status.DEFERRED, roomhash, manifest,
                                  num_fragments=len(objs))

        total_mb = sum(o.size for o in objs) / (1024 * 1024)
        if total_mb > self._s.max_audio_mb:
            raise RuntimeError(f"[{roomhash}] audio too large: {total_mb:.0f} MB")

        with make_workdir() as tmp:
            tmpdir = Path(tmp)
            local = [self._store.download(o, tmpdir / f"frag_{i:04d}.wav")
                     for i, o in enumerate(objs)]
            try:
                merged = concat_to_wav(local, tmpdir)
            except AudioError as e:
                raise RuntimeError(f"[{roomhash}] audio merge failed: {e}") from e

            logger.info("[%s] transcribing %d fragment(s)…", roomhash, len(objs))
            result = self._transcriber.transcribe(str(merged))

        payload = {
            "manifest": manifest,
            "roomhash": roomhash,
            "model": self._transcriber.model_name,
            "language": result.language,
            "language_probability": result.language_probability,
            "duration": result.duration,
            "num_fragments": len(objs),
            "source_keys": [o.key for o in objs],
            "text": result.text,
            "segments": [
                {"id": s.id, "start": s.start, "end": s.end, "text": s.text,
                 **({"words": s.words} if s.words else {})}
                for s in result.segments
            ],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        json_key = self._store.transcript_key(roomhash, manifest, "json")
        txt_key = self._store.transcript_key(roomhash, manifest, "txt")
        self._store.put_text(json_key, json.dumps(payload, ensure_ascii=False, indent=2),
                             "application/json")
        self._store.put_text(txt_key, result.text, "text/plain; charset=utf-8")
        logger.info("[%s] transcript done -> %s", roomhash, json_key)

        if self._summarizer.enabled:
            self._summarize(roomhash, manifest, result.text)

        return PipelineResult(Status.DONE, roomhash, manifest, json_key, len(objs))

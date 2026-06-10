import logging

from celery import Celery
from celery.signals import worker_process_init

from .config import get_settings
from .pipeline import Pipeline, Status
from .s3 import S3Store
from .transcriber import Transcriber

logger = logging.getLogger("celery_app")
settings = get_settings()

TRANSCRIPTION_QUEUE = settings.prefixed_queue("transcription")

celery_app = Celery(
    "corabea_transcriber",
    broker=settings.broker_url,
)

celery_app.conf.update(
    task_default_queue=TRANSCRIPTION_QUEUE,
    task_routes={
        "transcriber.transcribe_room": {
            "queue": TRANSCRIPTION_QUEUE,
            "routing_key": TRANSCRIPTION_QUEUE,
        }
    },
    task_ignore_result=True,
    result_backend=None,
    broker_connection_retry_on_startup=True,
    worker_concurrency=settings.celery_concurrency,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)


_pipeline: Pipeline | None = None


def _get_pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline(settings, S3Store(settings), Transcriber(settings))
    return _pipeline


@worker_process_init.connect
def _preload(**_kwargs):
    if settings.whisper_preload:
        logger.info("preloading whisper model at worker startup…")
        _get_pipeline()


@celery_app.task(
    name="transcriber.transcribe_room",
    bind=True,
    max_retries=settings.celery_max_retries,
)
def transcribe_room(self, roomhash: str) -> dict:
    """Transcribe one room's recordings and write the result to S3."""
    try:
        result = _get_pipeline().process_room(roomhash)
    except Exception as exc:
        logger.exception("transcribe_room failed for roomhash=%s", roomhash)
        raise self.retry(exc=exc, countdown=settings.requeue_delay_seconds)

    if result.status is Status.DEFERRED:
        raise self.retry(countdown=settings.requeue_delay_seconds)

    return {
        "status": result.status.value,
        "roomhash": roomhash,
        "manifest": result.manifest,
        "transcript_key": result.transcript_key,
        "num_fragments": result.num_fragments,
    }

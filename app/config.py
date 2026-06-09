from functools import lru_cache
from urllib.parse import quote_plus, urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_INITIAL_PROMPT = (
    "Trascrizione di una televisita medica in italiano tra operatore sanitario "
    "e paziente. Terminologia clinica: sintomi, diagnosi, terapia, farmaci, "
    "posologia, mg, anamnesi, pressione arteriosa, glicemia, referto, "
    "prescrizione, visita di controllo."
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        secrets_dir="/run/secrets",
    )

    whisper_model: str = "large-v3"
    whisper_compute_type: str = "int8"
    whisper_device: str = "cpu"
    whisper_cpu_threads: int = 0
    whisper_num_workers: int = 1
    whisper_download_root: str = "/models"
    whisper_language: str = "it"
    whisper_beam_size: int = 5
    whisper_vad_filter: bool = True
    whisper_word_timestamps: bool = False
    whisper_initial_prompt: str = DEFAULT_INITIAL_PROMPT
    whisper_condition_on_previous_text: bool = False
    whisper_preload: bool = True

    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket_name: str = "corabea"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False
    recordings_prefix: str = "recordings"
    transcriptions_prefix: str = "transcriptions"

    redis_url: str = "redis://redis:6379/0"
    redis_password: str = ""
    redis_use_ssl: bool = False
    celery_broker_url: str | None = None
    celery_queue_prefix: str = ""
    celery_concurrency: int = 1

    min_object_age_seconds: int = 120
    max_audio_mb: int = 1000
    requeue_delay_seconds: int = 120
    celery_max_retries: int = 20

    def _redis_url_with_auth(self) -> str:
        """Mirror corabea_api: inject the url-encoded password into REDIS_URL."""
        if not self.redis_password:
            return self.redis_url
        p = urlparse(self.redis_url)
        host = p.hostname or "localhost"
        port = p.port or 6379
        db = (p.path or "/0").lstrip("/") or "0"
        return f"redis://:{quote_plus(self.redis_password)}@{host}:{port}/{db}"

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self._redis_url_with_auth()

    def prefixed_queue(self, name: str) -> str:
        """Mirror corabea_api's _prefixed_queue for environment isolation."""
        prefix = (self.celery_queue_prefix or "").strip()
        return f"{prefix}{name}" if prefix else name


@lru_cache
def get_settings() -> Settings:
    return Settings()

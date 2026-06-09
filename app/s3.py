import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from .config import Settings

logger = logging.getLogger("s3")


@dataclass
class S3Object:
    key: str
    etag: str
    size: int
    last_modified: datetime


class S3Store:
    def __init__(self, settings: Settings):
        self._s = settings
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id or None,
            aws_secret_access_key=settings.s3_secret_access_key or None,
            region_name=settings.s3_region,
            use_ssl=settings.s3_use_ssl,
            config=Config(s3={"addressing_style": "path"}),
        )

    def list_recordings(self, roomhash: str) -> list[S3Object]:
        """List the WAV fragments under recordings/<roomhash>/."""
        prefix = f"{self._s.recordings_prefix}/{roomhash}/"
        objs: list[S3Object] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._s.s3_bucket_name, Prefix=prefix):
            for it in page.get("Contents", []):
                if not it["Key"].lower().endswith(".wav"):
                    continue
                objs.append(
                    S3Object(
                        key=it["Key"],
                        etag=it["ETag"].strip('"'),
                        size=it["Size"],
                        last_modified=it["LastModified"],
                    )
                )
        objs.sort(key=lambda o: o.last_modified)
        return objs

    def list_rooms(self) -> list[str]:
        """List the roomhash folders that have recordings (for ops/testing)."""
        prefix = f"{self._s.recordings_prefix}/"
        rooms: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(
            Bucket=self._s.s3_bucket_name, Prefix=prefix, Delimiter="/"
        ):
            for cp in page.get("CommonPrefixes", []):
                rooms.append(cp["Prefix"][len(prefix):].rstrip("/"))
        return rooms

    @staticmethod
    def manifest_hash(objs: list[S3Object]) -> str:
        """Deterministic id for a set of source fragments."""
        h = hashlib.sha256()
        for o in sorted(objs, key=lambda x: x.key):
            h.update(o.key.encode())
            h.update(b"\0")
            h.update(o.etag.encode())
            h.update(b"\0")
        return h.hexdigest()[:32]

    def newest_age_seconds(self, objs: list[S3Object]) -> float:
        newest = max(o.last_modified for o in objs)
        now = datetime.now(timezone.utc)
        return (now - newest).total_seconds()

    def transcript_key(self, roomhash: str, manifest: str, ext: str) -> str:
        return f"{self._s.transcriptions_prefix}/{roomhash}/{manifest}.{ext}"

    def transcript_exists(self, roomhash: str, manifest: str) -> bool:
        key = self.transcript_key(roomhash, manifest, "json")
        try:
            self._client.head_object(Bucket=self._s.s3_bucket_name, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def download(self, obj: S3Object, dst: Path) -> Path:
        logger.info("download s3://%s/%s -> %s", self._s.s3_bucket_name, obj.key, dst)
        self._client.download_file(self._s.s3_bucket_name, obj.key, str(dst))
        return dst

    def put_text(self, key: str, body: str, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._s.s3_bucket_name,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType=content_type,
        )
        logger.info("wrote s3://%s/%s", self._s.s3_bucket_name, key)

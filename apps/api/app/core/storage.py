"""S3-compatible private object storage, behind a provider-neutral interface.

Objects are write-once: keys are unique per upload and existing keys are never overwritten.
"""

import hashlib
import os
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO, Protocol

from app.core.config import get_settings
from app.core.errors import Conflict, ValidationFailed

CHUNK = 1024 * 1024


@dataclass(frozen=True)
class StoredObject:
    key: str
    size_bytes: int
    sha256: str
    content_type: str


class ObjectStorage(Protocol):
    def put(self, key: str, stream: BinaryIO, content_type: str) -> StoredObject: ...

    def open(self, key: str) -> Iterator[bytes]: ...

    def read_bytes(self, key: str) -> bytes: ...

    def presigned_get(self, key: str, *, filename: str, content_type: str) -> str | None: ...


def safe_filename(name: str) -> str:
    base = os.path.basename(name or "file")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "file"
    return cleaned[:150]


def build_key(tenant_id: uuid.UUID, area: str, owner_id: uuid.UUID, filename: str) -> str:
    return f"tenants/{tenant_id}/{area}/{owner_id}/{uuid.uuid4().hex}-{safe_filename(filename)}"


class _HashingReader:
    def __init__(self, stream: BinaryIO, limit: int):
        self._s = stream
        self._limit = limit
        self.size = 0
        self.sha = hashlib.sha256()

    def read(self, n: int = -1) -> bytes:
        chunk = self._s.read(n if n and n > 0 else CHUNK)
        self.size += len(chunk)
        if self.size > self._limit:
            raise ValidationFailed("File exceeds the maximum upload size")
        self.sha.update(chunk)
        return chunk


class LocalStorage:
    def __init__(self, root: str):
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self._root / key).resolve()
        if self._root not in p.parents:
            raise ValidationFailed("Invalid storage key")
        return p

    def put(self, key: str, stream: BinaryIO, content_type: str) -> StoredObject:
        path = self._path(key)
        if path.exists():
            raise Conflict("Object already exists; stored objects are immutable")
        path.parent.mkdir(parents=True, exist_ok=True)
        reader = _HashingReader(stream, get_settings().max_upload_bytes)
        tmp = path.with_suffix(path.suffix + ".part")
        try:
            with open(tmp, "wb") as fh:
                while chunk := reader.read(CHUNK):
                    fh.write(chunk)
            os.replace(tmp, path)
            os.chmod(path, 0o440)
        finally:
            if tmp.exists():
                tmp.unlink()
        return StoredObject(key=key, size_bytes=reader.size, sha256=reader.sha.hexdigest(), content_type=content_type)

    def open(self, key: str) -> Iterator[bytes]:
        with open(self._path(key), "rb") as fh:
            while chunk := fh.read(CHUNK):
                yield chunk

    def read_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def presigned_get(self, key: str, *, filename: str, content_type: str) -> str | None:
        return None


class S3Storage:
    def __init__(self) -> None:
        import boto3

        s = get_settings()
        self._bucket = s.s3_bucket
        self._ttl = s.presigned_url_ttl_seconds
        self._client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url,
            aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key,
            region_name=s.s3_region,
        )

    def put(self, key: str, stream: BinaryIO, content_type: str) -> StoredObject:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            raise Conflict("Object already exists; stored objects are immutable")
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in ("404", "NoSuchKey", "NotFound"):
                raise
        reader = _HashingReader(stream, get_settings().max_upload_bytes)
        self._client.upload_fileobj(
            reader, self._bucket, key,
            ExtraArgs={"ContentType": content_type, "ServerSideEncryption": "AES256"},
        )
        return StoredObject(key=key, size_bytes=reader.size, sha256=reader.sha.hexdigest(), content_type=content_type)

    def open(self, key: str) -> Iterator[bytes]:
        body = self._client.get_object(Bucket=self._bucket, Key=key)["Body"]
        yield from body.iter_chunks(CHUNK)

    def read_bytes(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def presigned_get(self, key: str, *, filename: str, content_type: str) -> str | None:
        return self._client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ResponseContentDisposition": f'attachment; filename="{safe_filename(filename)}"',
                "ResponseContentType": content_type,
            },
            ExpiresIn=self._ttl,
        )


@lru_cache
def get_storage() -> ObjectStorage:
    s = get_settings()
    if s.storage_backend == "s3":
        return S3Storage()
    return LocalStorage(s.storage_local_root)

"""S3-compatible source-artifact storage for development and production adapters."""

from __future__ import annotations

import io
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

from minio import Minio


@dataclass(frozen=True)
class StoredArtifact:
    object_key: str
    content_type: str
    byte_size: int


class MinioArtifactStorage:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str) -> None:
        self.bucket = bucket
        self.client = Minio(
            endpoint.removeprefix("http://").removeprefix("https://"),
            access_key=access_key,
            secret_key=secret_key,
            secure=endpoint.startswith("https://"),
        )

    def put(self, user_id: UUID, import_id: UUID, filename: str, content: bytes) -> StoredArtifact:
        suffix = filename.rsplit(".", 1)[-1].lower()
        content_type = "text/csv" if suffix == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        object_key = f"imports/{user_id}/{import_id}/statement.{suffix}"
        self.client.put_object(self.bucket, object_key, io.BytesIO(content), len(content), content_type=content_type)
        return StoredArtifact(object_key=object_key, content_type=content_type, byte_size=len(content))

    def delete(self, object_key: str) -> None:
        self.client.remove_object(self.bucket, object_key)

    def iter_object(self, object_key: str) -> Iterator[bytes]:
        response = self.client.get_object(self.bucket, object_key)
        try:
            yield from response.stream(32 * 1024)
        finally:
            response.close()
            response.release_conn()

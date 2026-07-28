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
        content_type = {
            "csv": "text/csv",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "pdf": "application/pdf",
        }.get(suffix, "application/octet-stream")
        object_key = f"imports/{user_id}/{import_id}/statement.{suffix}"
        self.client.put_object(self.bucket, object_key, io.BytesIO(content), len(content), content_type=content_type)
        return StoredArtifact(object_key=object_key, content_type=content_type, byte_size=len(content))

    def delete(self, object_key: str) -> None:
        self.client.remove_object(self.bucket, object_key)

    def put_gmail_message(self, user_id: UUID, mailbox_id: UUID, message_id: str, content: bytes) -> StoredArtifact:
        object_key = f"gmail/{user_id}/{mailbox_id}/{message_id}.eml"
        self.client.put_object(self.bucket, object_key, io.BytesIO(content), len(content), content_type="message/rfc822")
        return StoredArtifact(object_key=object_key, content_type="message/rfc822", byte_size=len(content))

    def put_gmail_attachment(self, user_id: UUID, mailbox_id: UUID, message_id: str, ordinal: int, content: bytes) -> StoredArtifact:
        object_key = f"gmail/{user_id}/{mailbox_id}/{message_id}/attachment-{ordinal}.pdf"
        self.client.put_object(self.bucket, object_key, io.BytesIO(content), len(content), content_type="application/pdf")
        return StoredArtifact(object_key=object_key, content_type="application/pdf", byte_size=len(content))

    def iter_object(self, object_key: str) -> Iterator[bytes]:
        response = self.client.get_object(self.bucket, object_key)
        try:
            yield from response.stream(32 * 1024)
        finally:
            response.close()
            response.release_conn()

    def get_bytes(self, object_key: str) -> bytes:
        return b"".join(self.iter_object(object_key))

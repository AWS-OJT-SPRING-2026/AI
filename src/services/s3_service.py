"""
S3 Service — handles all AWS S3 upload operations for EduCare documents.

Reads credentials from environment:
  AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION (default: ap-southeast-1), AWS_BUCKET_NAME

S3 key format:
  documents/{type_lower}/{user_id}_{timestamp}_{original_filename}
"""
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError


class S3Service:
    def __init__(self):
        self._access_key = os.getenv("AWS_ACCESS_KEY", "")
        self._secret_key = os.getenv("AWS_SECRET_KEY", "")
        self.region = os.getenv("AWS_REGION", "ap-southeast-1")
        self.bucket_name = os.getenv("AWS_BUCKET_NAME", "")

        self._client = boto3.client(
            "s3",
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self.region,
        )

    def upload_document(
        self,
        file_obj,
        user_id: int,
        doc_type: str,
        original_filename: str,
    ) -> tuple[str, str]:
        """
        Stream a file-like object directly to S3.

        Args:
            file_obj:          Readable file-like object (UploadFile.file or open(..., "rb")).
            user_id:           ID of the uploader (teacher).
            doc_type:          "THEORY" or "QUESTION" — determines S3 prefix.
            original_filename: Original file name (used in the S3 key).

        Returns:
            (s3_key, public_url)

        Raises:
            RuntimeError: wraps botocore ClientError on upload failure.
        """
        if not self.bucket_name:
            raise RuntimeError("AWS_BUCKET_NAME environment variable is not set.")

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        safe_name = os.path.basename(original_filename)
        type_lower = doc_type.lower()  # "theory" or "question"
        s3_key = f"documents/{type_lower}/{user_id}_{timestamp}_{safe_name}"

        try:
            self._client.upload_fileobj(
                file_obj,
                self.bucket_name,
                s3_key,
                ExtraArgs={"ContentType": "application/pdf"},
            )
        except ClientError as exc:
            raise RuntimeError(f"S3 upload failed for key '{s3_key}': {exc}") from exc

        public_url = (
            f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
        )
        return s3_key, public_url


    def delete_document(self, file_url_or_key: str) -> bool:
        """
        Delete a document from S3.

        Accepts either a full S3 HTTPS URL or a raw S3 key.
        Returns True on successful deletion.
        Returns False (with a warning log) when the object does not exist —
        note: S3's delete_object is idempotent and never raises NoSuchKey,
        so False is returned only when we explicitly detect a missing object
        via a head_object pre-check.

        Raises:
            RuntimeError: on any unexpected AWS ClientError (permissions, network, etc.)
        """
        import logging

        if not self.bucket_name:
            raise RuntimeError("AWS_BUCKET_NAME environment variable is not set.")

        # Extract the raw key when a full URL is given
        # URL format: https://{bucket}.s3.{region}.amazonaws.com/{key}
        if file_url_or_key.startswith("http"):
            s3_key = file_url_or_key.split(".amazonaws.com/", 1)[-1]
        else:
            s3_key = file_url_or_key

        # Check existence first so we can return False instead of silently
        # deleting a non-existent object (delete_object is always 204 on S3)
        try:
            self._client.head_object(Bucket=self.bucket_name, Key=s3_key)
        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            if error_code in ("404", "NoSuchKey"):
                logging.warning(
                    "[S3] File not found, skipping S3 delete (already removed?): %s", s3_key
                )
                return False
            raise RuntimeError(
                f"S3 head_object failed for key '{s3_key}': {exc}"
            ) from exc

        try:
            self._client.delete_object(Bucket=self.bucket_name, Key=s3_key)
        except ClientError as exc:
            raise RuntimeError(
                f"S3 delete_object failed for key '{s3_key}': {exc}"
            ) from exc

        return True


# Singleton — import this instance in other modules
s3_service = S3Service()

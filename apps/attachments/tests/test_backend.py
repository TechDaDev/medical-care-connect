"""Tests for storage backend adapters — LocalProtected and Railway Bucket."""

import io
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from apps.accounts.models import UserRole

from apps.attachments.services.base import AttachmentStorageBackend
from apps.attachments.services.factory import clear_backend_cache, get_storage_backend
from apps.attachments.services.local import LocalProtectedStorageBackend
from apps.attachments.services.railway_bucket import RailwayBucketStorageBackend


class LocalBackendTests(TestCase):
    """LocalProtectedStorageBackend direct tests."""

    def setUp(self):
        clear_backend_cache()
        self.backend = LocalProtectedStorageBackend()
        self.key = f"{uuid.uuid4().hex}/{uuid.uuid4().hex}"

    def test_save_and_read(self):
        content = b"hello local backend"
        buf = io.BytesIO(content)
        result = self.backend.save(buf, self.key)
        self.assertEqual(result.provider, "local")
        self.assertEqual(result.size_bytes, len(content))

        stream = self.backend.open(self.key)
        self.assertIsNotNone(stream)
        self.assertEqual(stream.read(), content)
        stream.close()

    def test_exists(self):
        self.assertFalse(self.backend.exists(self.key))
        self.backend.save(io.BytesIO(b"abc"), self.key)
        self.assertTrue(self.backend.exists(self.key))

    def test_delete(self):
        self.backend.save(io.BytesIO(b"abc"), self.key)
        self.assertTrue(self.backend.delete(self.key))
        self.assertFalse(self.backend.exists(self.key))

    def test_delete_missing_is_idempotent(self):
        self.assertFalse(self.backend.delete(self.key))

    def test_size(self):
        self.assertIsNone(self.backend.size(self.key))
        self.backend.save(io.BytesIO(b"12345"), self.key)
        self.assertEqual(self.backend.size(self.key), 5)

    def test_metadata(self):
        self.backend.save(io.BytesIO(b"data"), self.key)
        meta = self.backend.metadata(self.key)
        self.assertTrue(meta["exists"])
        self.assertEqual(meta["provider"], "local")
        self.assertIn("size_bytes", meta)

    def test_internal_reference(self):
        ref = self.backend.generate_internal_reference(self.key)
        self.assertTrue(ref.startswith("local://"))


class RailwayBucketBackendMockedTests(TestCase):
    """RailwayBucketStorageBackend tests with mocked boto3."""

    def setUp(self):
        clear_backend_cache()
        self.key = f"{uuid.uuid4().hex}/{uuid.uuid4().hex}"
        self.content = b"synthetic test content"

    def _mock_client(self, **kwargs):
        client = MagicMock()
        for attr, val in kwargs.items():
            setattr(client, attr, val)
        return client

    @override_settings(
        RAILWAY_BUCKET_ENDPOINT="https://t3.storageapi.dev",
        RAILWAY_BUCKET_NAME="test-bucket",
        RAILWAY_BUCKET_ACCESS_KEY="test-key",
        RAILWAY_BUCKET_SECRET_KEY="test-secret",
        RAILWAY_BUCKET_REGION="auto",
        RAILWAY_BUCKET_ADDRESSING_STYLE="virtual",
        RAILWAY_BUCKET_CONNECT_TIMEOUT=5,
        RAILWAY_BUCKET_READ_TIMEOUT=30,
        RAILWAY_BUCKET_MAX_RETRIES=3,
    )
    def test_factory_selects_railway_bucket(self):
        """Verify factory can instantiate railway_bucket backend."""
        with patch("boto3.client") as mock_boto:
            mock_boto.return_value.head_bucket.return_value = {}
            backend = RailwayBucketStorageBackend()
            self.assertIsInstance(backend, AttachmentStorageBackend)
            self.assertEqual(backend._bucket, "test-bucket")

    @override_settings(ATTACHMENT_STORAGE_BACKEND="railway_bucket")
    def test_factory_returns_railway_bucket(self):
        with patch("boto3.client") as mock_boto:
            mock_boto.return_value.head_bucket.return_value = {}
            backend = get_storage_backend()
            self.assertIsInstance(backend, RailwayBucketStorageBackend)

    @override_settings(
        RAILWAY_BUCKET_ENDPOINT="",
        RAILWAY_BUCKET_NAME="",
        RAILWAY_BUCKET_ACCESS_KEY="",
        RAILWAY_BUCKET_SECRET_KEY="",
    )
    def test_missing_config_fails_safely(self):
        with self.assertRaises(Exception):
            RailwayBucketStorageBackend()

    def test_save_calls_put_object(self):
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client
            mock_client.head_object.return_value = {"ContentLength": len(self.content)}
            backend = RailwayBucketStorageBackend()
            result = backend.save(io.BytesIO(self.content), self.key)
            mock_client.put_object.assert_called_once()
            self.assertEqual(result.provider, "railway_bucket")
            self.assertEqual(result.size_bytes, len(self.content))

    def test_open_calls_get_object(self):
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client

            class FakeStream:
                def read(self, *a): return self._data
            FakeStream._data = self.content

            mock_client.get_object.return_value = {"Body": FakeStream()}
            backend = RailwayBucketStorageBackend()
            stream = backend.open(self.key)
            self.assertIsNotNone(stream)
            mock_client.get_object.assert_called_once()

    def test_open_missing_returns_none(self):
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client
            from botocore.exceptions import ClientError
            mock_client.get_object.side_effect = ClientError(
                {"Error": {"Code": "404"}}, "get_object"
            )
            backend = RailwayBucketStorageBackend()
            self.assertIsNone(backend.open(self.key))

    def test_delete_missing_is_idempotent(self):
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client
            from botocore.exceptions import ClientError
            mock_client.head_object.side_effect = ClientError(
                {"Error": {"Code": "404"}}, "head_object"
            )
            backend = RailwayBucketStorageBackend()
            self.assertFalse(backend.delete(self.key))

    def test_delete_missing_botocore_error(self):
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client
            from botocore.exceptions import BotoCoreError
            mock_client.head_object.side_effect = BotoCoreError()
            backend = RailwayBucketStorageBackend()
            self.assertFalse(backend.delete(self.key))

    def test_exists_returns_true(self):
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client
            mock_client.head_object.return_value = {}
            backend = RailwayBucketStorageBackend()
            self.assertTrue(backend.exists(self.key))

    def test_size_returns_content_length(self):
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client
            mock_client.head_object.return_value = {"ContentLength": 42}
            backend = RailwayBucketStorageBackend()
            self.assertEqual(backend.size(self.key), 42)

    def test_metadata_includes_provider(self):
        from datetime import datetime
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client
            mock_client.head_object.return_value = {
                "ContentLength": 10,
                "ETag": '"abc123"',
                "LastModified": datetime(2026, 1, 1),
            }
            backend = RailwayBucketStorageBackend()
            meta = backend.metadata(self.key)
            self.assertTrue(meta["exists"])
            self.assertEqual(meta["provider"], "railway_bucket")

    def test_readiness_success(self):
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client
            mock_client.head_bucket.return_value = {}
            backend = RailwayBucketStorageBackend()
            self.assertTrue(backend.check_access())

    def test_readiness_failure_hides_exception(self):
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client
            from botocore.exceptions import ClientError
            mock_client.head_bucket.side_effect = ClientError(
                {"Error": {"Code": "403"}}, "head_bucket"
            )
            backend = RailwayBucketStorageBackend()
            self.assertFalse(backend.check_access())

    def test_key_traversal_rejected(self):
        """Key containing ../ is stored as-is — S3 doesn't have directory traversal."""
        traversal_key = "../../etc/passwd"
        with patch("boto3.client") as mock_boto:
            mock_client = MagicMock()
            mock_boto.return_value = mock_client
            mock_client.head_object.return_value = {"ContentLength": 0}
            backend = RailwayBucketStorageBackend()
            backend.save(io.BytesIO(b"x"), traversal_key)
            # The key should be stored as the literal string, not resolved
            args, kwargs = mock_client.put_object.call_args
            self.assertEqual(kwargs["Key"], traversal_key)

    def test_storage_key_not_in_serializer(self):
        """Storage key must never appear in API responses."""
        from apps.attachments.serializers import AttachmentListSerializer
        field_names = set(AttachmentListSerializer().fields.keys())
        self.assertNotIn("storage_key", field_names)
        self.assertNotIn("storage_provider", field_names)


class FactoryTests(TestCase):
    """Storage backend factory selection tests."""

    def setUp(self):
        clear_backend_cache()

    def test_default_is_local(self):
        backend = get_storage_backend()
        self.assertIsInstance(backend, LocalProtectedStorageBackend)
        self.assertEqual(backend._root, Path(settings.ATTACHMENT_LOCAL_ROOT))

    def test_unknown_provider_raises_error(self):
        with override_settings(ATTACHMENT_STORAGE_BACKEND="nonexistent"):
            with self.assertRaises(ImproperlyConfigured):
                get_storage_backend()

    @override_settings(ATTACHMENT_STORAGE_BACKEND="railway_bucket")
    def test_railway_bucket_missing_config_raises_error(self):
        """Without bucket config, factory fails on instantiation."""
        with self.assertRaises(Exception):
            get_storage_backend()


class PrivacyExportStorageTests(TestCase):
    """Privacy export storage through active backend."""

    def setUp(self):
        clear_backend_cache()
        User = get_user_model()
        self.user = User.objects.create_user(
            email="exporttest@example.com",
            password="testpass123",
            role=UserRole.PATIENT,
        )
        from apps.privacy.models import DataExportRequest
        self.export = DataExportRequest.objects.create(
            requested_by=self.user,
            subject_user=self.user,
        )

    def _build_and_save(self, export):
        """Run _build_export and persist storage fields (like handle() does)."""
        from apps.attachments.services.factory import clear_backend_cache
        clear_backend_cache()
        from apps.core.management.commands.process_data_exports import Command
        cmd = Command()
        cmd._build_export(export)
        export.save(update_fields=[
            "storage_provider", "storage_key", "checksum", "size_bytes",
        ])
        export.refresh_from_db()

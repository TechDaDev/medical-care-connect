# Attachment Storage Architecture

## Provider-Neutral Abstraction

All attachment I/O goes through `AttachmentStorageBackend` (interface in
`apps/attachments/services/base.py`). Application code never calls
`FileSystemStorage` or any provider-specific API directly.

### Interface

```python
class AttachmentStorageBackend(ABC):
    def save(file, storage_key) -> StoredObject
    def open(storage_key) -> Optional[BinaryIO]
    def delete(storage_key) -> bool
    def exists(storage_key) -> bool
    def size(storage_key) -> Optional[int]
    def metadata(storage_key) -> dict
    def generate_internal_reference(storage_key) -> str
```

## Current Implementation: LocalProtectedStorageBackend

- Stores files under `ATTACHMENT_LOCAL_ROOT` (default `protected_attachments/`)
- Files organized as `<root>/<prefix>/<storage_key>`
- Storage is outside `STATIC_ROOT` and `MEDIA_ROOT`
- Not served through Nginx or Django static file server
- Only accessible through authorized download endpoint

## Future: Railway Bucket Adapter

A future `RailwayBucketStorageBackend` will implement the same interface
using Railway's S3-compatible Bucket API. Model and API contracts will
remain unchanged when the adapter is introduced.

## Storage Keys

- Generated server-side using `consultation_id_hex/random_uuid_hex`
- Never derived from original filename
- Never exposed through public serializers
- Never stored as absolute filesystem paths in the database
- The database stores only `storage_provider` name and opaque `storage_key`

## Migration Path

A future `migrate_attachment_storage` management command will:

1. Copy object from source to destination provider
2. Verify SHA-256 hash
3. Update `storage_provider` and `storage_key` transactionally
4. Preserve attachment ID and API contract
5. Support `--dry-run` mode
6. Delete source only after verification
7. Be resumable (skip already-migrated keys)

from app.models.schemas import StoredAwsCredentials


class SessionStore:
    """Single-user in-memory session for verified AWS credentials."""

    def __init__(self) -> None:
        self._credentials: StoredAwsCredentials | None = None

    @property
    def is_verified(self) -> bool:
        return self._credentials is not None

    @property
    def credentials(self) -> StoredAwsCredentials | None:
        return self._credentials

    def set_credentials(self, credentials: StoredAwsCredentials) -> None:
        self._credentials = credentials

    def clear(self) -> None:
        self._credentials = None

from fastapi import HTTPException, status


def credentials_required() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="AWS credentials not verified. Complete onboarding first.",
    )


def bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def service_unavailable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)


def format_error(exc: BaseException) -> str:
    """Flatten ExceptionGroup / nested errors into a user-safe message."""
    if isinstance(exc, BaseExceptionGroup):
        parts = [format_error(e) for e in exc.exceptions if e is not None]
        return "; ".join(part for part in parts if part) or str(exc)
    return str(exc)

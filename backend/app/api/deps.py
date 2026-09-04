"""FastAPI dependencies: DB session, current user (JWT or API key), project ownership, rate limits."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, Path, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import NotFoundError, PermissionDeniedError, UnauthorizedError
from app.core.security import decode_token, hash_api_key
from app.db.session import get_db
from app.models.project import Project
from app.models.user import ApiKey, User, UserSession

bearer = HTTPBearer(auto_error=False)


def _rate_key(request: Request) -> str:
    user = getattr(request.state, "user_id", None)
    return f"user:{user}" if user else get_remote_address(request)


limiter = Limiter(key_func=_rate_key, default_limits=[settings.rate_limit_default], storage_uri=settings.redis_url, headers_enabled=False)

# scope="function": the session's exit code (COMMIT) must run *before* the response is sent.
# FastAPI >= 0.106 defaults yield-dependencies to request scope, i.e. teardown after the response,
# which let a client receive a login/signup response before its new session row was committed
# and get a 401 on the immediately following /auth/me.
DB = Annotated[AsyncSession, Depends(get_db, scope="function")]


async def get_current_user(
    request: Request,
    db: DB,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> User:
    user: User | None = None
    if creds and creds.scheme.lower() == "bearer":
        try:
            payload = decode_token(creds.credentials, "access")
        except ValueError as exc:
            raise UnauthorizedError("Invalid or expired token") from exc
        session = await db.get(UserSession, uuid.UUID(payload["sid"]))
        if session is None or session.revoked_at is not None or session.expires_at < datetime.now(UTC):
            raise UnauthorizedError("Session expired or revoked")
        user = await db.get(User, uuid.UUID(payload["sub"]))
    elif x_api_key:
        key = (await db.execute(select(ApiKey).where(ApiKey.key_hash == hash_api_key(x_api_key)))).scalar_one_or_none()
        if key is None or key.revoked_at is not None or (key.expires_at and key.expires_at < datetime.now(UTC)):
            raise UnauthorizedError("Invalid API key")
        key.last_used_at = datetime.now(UTC)
        user = await db.get(User, key.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Authentication required")
    request.state.user_id = str(user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_owned_project(project_id: Annotated[uuid.UUID, Path()], user: CurrentUser, db: DB) -> Project:
    project = (
        await db.execute(select(Project).where(Project.id == project_id).options(selectinload(Project.research)))
    ).scalar_one_or_none()
    if project is None:
        raise NotFoundError("Project not found")
    if project.owner_id != user.id and not user.is_superuser:
        raise PermissionDeniedError("You do not have access to this project")
    return project


OwnedProject = Annotated[Project, Depends(get_owned_project)]


async def require_superuser(user: CurrentUser) -> User:
    if not user.is_superuser:
        raise PermissionDeniedError("Admin access required")
    return user

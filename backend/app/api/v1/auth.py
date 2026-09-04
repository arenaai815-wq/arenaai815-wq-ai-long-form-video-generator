from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, limiter
from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, UnauthorizedError, ValidationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.enums import CreditTransactionKind
from app.models.user import ApiKey, User, UserSession
from app.schemas.auth import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyPublic,
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    SessionPublic,
    SignupRequest,
    TokenPair,
    UserPublic,
    UserUpdate,
)
from app.schemas.common import Message
from app.services.billing_service import add_credits, ensure_subscription

router = APIRouter()


async def _issue_tokens(db: DB, user: User, request: Request) -> TokenPair:
    session = UserSession(
        user_id=user.id,
        refresh_token_hash="pending",
        user_agent=(request.headers.get("user-agent") or "")[:512],
        ip_address=(request.client.host if request.client else None),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(session)
    await db.flush()
    refresh = create_refresh_token(user.id, session.id)
    session.refresh_token_hash = hash_refresh_token(refresh)
    session.last_used_at = datetime.now(UTC)
    user.last_login_at = datetime.now(UTC)
    return TokenPair(
        access_token=create_access_token(user.id, session.id),
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/signup", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_auth)
async def signup(request: Request, body: SignupRequest, db: DB) -> TokenPair:
    email = body.email.lower()
    exists = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if exists:
        raise ConflictError("An account with this email already exists")
    user = User(email=email, password_hash=hash_password(body.password), full_name=body.full_name, is_verified=not settings.is_production)
    db.add(user)
    await db.flush()
    await ensure_subscription(db, user)
    await add_credits(db, user, settings.free_plan_credits, CreditTransactionKind.GRANT, description="Welcome credits", reference=f"welcome:{user.id}")
    return await _issue_tokens(db, user, request)


@router.post("/login", response_model=TokenPair)
@limiter.limit(settings.rate_limit_auth)
async def login(request: Request, body: LoginRequest, db: DB) -> TokenPair:
    user = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise UnauthorizedError("Invalid email or password")
    if not user.is_active:
        raise UnauthorizedError("Account disabled")
    return await _issue_tokens(db, user, request)


@router.post("/refresh", response_model=TokenPair)
@limiter.limit("60/minute")
async def refresh(request: Request, body: RefreshRequest, db: DB) -> TokenPair:
    try:
        payload = decode_token(body.refresh_token, "refresh")
    except ValueError as exc:
        raise UnauthorizedError("Invalid refresh token") from exc
    session = await db.get(UserSession, uuid.UUID(payload["sid"]))
    if session is None or session.revoked_at or session.expires_at < datetime.now(UTC):
        raise UnauthorizedError("Session expired")
    if session.refresh_token_hash != hash_refresh_token(body.refresh_token):
        # Token reuse -> revoke the whole session (possible theft)
        session.revoked_at = datetime.now(UTC)
        raise UnauthorizedError("Refresh token reuse detected; please sign in again")
    user = await db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Account unavailable")
    # Rotate refresh token
    new_refresh = create_refresh_token(user.id, session.id)
    session.refresh_token_hash = hash_refresh_token(new_refresh)
    session.last_used_at = datetime.now(UTC)
    session.expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    return TokenPair(access_token=create_access_token(user.id, session.id), refresh_token=new_refresh, expires_in=settings.access_token_expire_minutes * 60)


@router.post("/logout", response_model=Message)
async def logout(request: Request, user: CurrentUser, db: DB) -> Message:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            payload = decode_token(auth.split(" ", 1)[1], "access")
            session = await db.get(UserSession, uuid.UUID(payload["sid"]))
            if session:
                session.revoked_at = datetime.now(UTC)
        except ValueError:
            pass
    return Message(message="Signed out")


@router.get("/me", response_model=UserPublic)
async def me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserPublic)
async def update_me(body: UserUpdate, user: CurrentUser, db: DB) -> User:
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.avatar_url is not None:
        user.avatar_url = body.avatar_url
    if body.preferences is not None:
        user.preferences = {**(user.preferences or {}), **body.preferences}
    await db.flush()
    return user


@router.post("/me/password", response_model=Message)
async def change_password(body: ChangePasswordRequest, user: CurrentUser, db: DB) -> Message:
    if not verify_password(body.current_password, user.password_hash):
        raise ValidationError("Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    # Revoke every other session
    sessions = (await db.execute(select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)))).scalars().all()
    for s in sessions:
        s.revoked_at = datetime.now(UTC)
    return Message(message="Password updated. Please sign in again.")


@router.get("/sessions", response_model=list[SessionPublic])
async def list_sessions(request: Request, user: CurrentUser, db: DB) -> list[SessionPublic]:
    current_sid = None
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            current_sid = decode_token(auth.split(" ", 1)[1], "access")["sid"]
        except ValueError:
            pass
    rows = (
        await db.execute(
            select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None), UserSession.expires_at > datetime.now(UTC)).order_by(UserSession.created_at.desc())
        )
    ).scalars().all()
    return [SessionPublic.model_validate(s).model_copy(update={"is_current": str(s.id) == current_sid}) for s in rows]


@router.delete("/sessions/{session_id}", response_model=Message)
async def revoke_session(session_id: uuid.UUID, user: CurrentUser, db: DB) -> Message:
    s = await db.get(UserSession, session_id)
    if s is None or s.user_id != user.id:
        raise NotFoundError("Session not found")
    s.revoked_at = datetime.now(UTC)
    return Message(message="Session revoked")


# --- API keys ----------------------------------------------------------------


@router.get("/api-keys", response_model=list[ApiKeyPublic])
async def list_api_keys(user: CurrentUser, db: DB) -> list[ApiKey]:
    return list((await db.execute(select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc()))).scalars().all())


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_key(body: ApiKeyCreate, user: CurrentUser, db: DB) -> ApiKeyCreated:
    plaintext, prefix, digest = generate_api_key()
    key = ApiKey(
        user_id=user.id, name=body.name, key_prefix=prefix, key_hash=digest, scopes=body.scopes,
        expires_at=(datetime.now(UTC) + timedelta(days=body.expires_in_days)) if body.expires_in_days else None,
    )
    db.add(key)
    await db.flush()
    return ApiKeyCreated(**ApiKeyPublic.model_validate(key).model_dump(), key=plaintext)


@router.delete("/api-keys/{key_id}", response_model=Message)
async def revoke_key(key_id: uuid.UUID, user: CurrentUser, db: DB) -> Message:
    key = await db.get(ApiKey, key_id)
    if key is None or key.user_id != user.id:
        raise NotFoundError("API key not found")
    key.revoked_at = datetime.now(UTC)
    return Message(message="API key revoked")

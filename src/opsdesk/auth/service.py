from __future__ import annotations

import uuid
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opsdesk.auth.repository import AuthRepository
from opsdesk.auth.security import (
    get_password_service,
    hash_session_token,
    make_throttle_key,
    new_csrf_secret,
    new_session_token,
    normalize_email,
)
from opsdesk.core.config import Settings
from opsdesk.core.errors import AuthenticationError, ConflictError, RateLimitError
from opsdesk.db.base import utc_now
from opsdesk.db.models import LoginThrottle, User, UserSession
from opsdesk.observability.logging import get_logger
from opsdesk.observability.metrics import OpsMetrics
from opsdesk.observability.tracing import Telemetry


@dataclass(slots=True)
class AuthPrincipal:
    user: User
    session: UserSession


@dataclass(frozen=True, slots=True)
class LoginResult:
    principal: AuthPrincipal
    raw_session_token: str


class AuthService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        metrics: OpsMetrics | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.repository = AuthRepository(db)
        self.passwords = get_password_service()
        self.metrics = metrics
        self.telemetry = telemetry

    def register(self, email: str, password: str, request_id: str) -> User:
        normalized_email = normalize_email(email)
        if self.repository.find_user_by_email(normalized_email) is not None:
            raise ConflictError("An account with those details cannot be created")
        user = User(
            email=normalized_email,
            password_hash=self.passwords.hash(password),
            role_key="user",
            is_active=True,
        )
        self.repository.add_user(user)
        try:
            self.db.flush()
            self.repository.add_audit(
                event_type="user.registered",
                actor_user_id=user.id,
                target_type="user",
                target_id=str(user.id),
                request_id=request_id,
            )
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise ConflictError("An account with those details cannot be created") from error
        get_logger().info("user.registered", event_name="user.registered", user_id=str(user.id))
        return user

    def login(
        self,
        email: str,
        password: str,
        client_address: str,
        request_id: str,
    ) -> LoginResult:
        context = self.telemetry.span("auth.login") if self.telemetry else nullcontext()
        with context:
            return self._login(email, password, client_address, request_id)

    def _login(
        self,
        email: str,
        password: str,
        client_address: str,
        request_id: str,
    ) -> LoginResult:
        now = utc_now()
        normalized_email = normalize_email(email)
        throttle_key = make_throttle_key(normalized_email, client_address, self.settings)
        throttle = self.repository.find_throttle_for_update(throttle_key)
        if (
            throttle is not None
            and throttle.locked_until is not None
            and throttle.locked_until > now
        ):
            self.repository.add_audit(
                event_type="rate_limit.exceeded",
                actor_user_id=None,
                request_id=request_id,
                target_type="authentication",
            )
            self.db.commit()
            get_logger().warning(
                "rate_limit.exceeded", event_name="rate_limit.exceeded", outcome="blocked"
            )
            if self.metrics:
                self.metrics.login_attempts.labels(outcome="rate_limited").inc()
            raise RateLimitError()

        user = self.repository.find_user_by_email(normalized_email)
        if user is None:
            self.passwords.consume_dummy_verification(password)
            self._record_login_failure(throttle_key, throttle, now, request_id, None)
            if self.metrics:
                self.metrics.login_attempts.labels(outcome="invalid_credentials").inc()
            raise AuthenticationError()
        if not self.passwords.verify(user.password_hash, password) or not user.is_active:
            self._record_login_failure(throttle_key, throttle, now, request_id, user.id)
            if self.metrics:
                self.metrics.login_attempts.labels(outcome="invalid_credentials").inc()
            raise AuthenticationError()

        self.repository.clear_throttle(throttle_key)
        raw_token = new_session_token()
        session = UserSession(
            token_hash=hash_session_token(raw_token),
            user_id=user.id,
            csrf_secret=new_csrf_secret(),
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(minutes=self.settings.session_absolute_minutes),
        )
        self.repository.add_session(session)
        self.db.flush()
        self.repository.add_audit(
            event_type="user.login_succeeded",
            actor_user_id=user.id,
            request_id=request_id,
            target_type="session",
            target_id=str(session.id),
        )
        self.db.commit()
        get_logger().info(
            "user.login_succeeded",
            event_name="user.login_succeeded",
            user_id=str(user.id),
        )
        if self.metrics:
            self.metrics.login_attempts.labels(outcome="succeeded").inc()
        return LoginResult(AuthPrincipal(user=user, session=session), raw_token)

    def authenticate_session(self, raw_token: str) -> AuthPrincipal:
        now = utc_now()
        user_session = self.repository.find_session_by_token_hash(hash_session_token(raw_token))
        if user_session is None or user_session.revoked_at is not None:
            raise AuthenticationError()
        idle_deadline = user_session.last_seen_at + timedelta(
            minutes=self.settings.session_idle_minutes
        )
        if (
            user_session.expires_at <= now
            or idle_deadline <= now
            or not user_session.user.is_active
        ):
            user_session.revoked_at = now
            self.db.commit()
            raise AuthenticationError()
        touch_after = user_session.last_seen_at + timedelta(
            seconds=self.settings.session_touch_interval_seconds
        )
        if touch_after <= now:
            user_session.last_seen_at = now
            self.db.commit()
        return AuthPrincipal(user=user_session.user, session=user_session)

    def logout(self, principal: AuthPrincipal, request_id: str) -> None:
        if principal.session.revoked_at is None:
            principal.session.revoked_at = utc_now()
        self.repository.add_audit(
            event_type="user.logout_succeeded",
            actor_user_id=principal.user.id,
            request_id=request_id,
            target_type="session",
            target_id=str(principal.session.id),
        )
        self.db.commit()
        get_logger().info(
            "user.logout_succeeded",
            event_name="user.logout_succeeded",
            user_id=str(principal.user.id),
        )

    def _record_login_failure(
        self,
        throttle_key: str,
        throttle: LoginThrottle | None,
        now: datetime,
        request_id: str,
        user_id: uuid.UUID | None,
    ) -> None:
        window = timedelta(seconds=self.settings.login_window_seconds)
        if throttle is None:
            throttle = LoginThrottle(
                key=throttle_key,
                failure_count=0,
                window_started_at=now,
                updated_at=now,
            )
            self.repository.add_throttle(throttle)
        elif throttle.window_started_at + window <= now:
            throttle.failure_count = 0
            throttle.window_started_at = now
            throttle.locked_until = None
        throttle.failure_count += 1
        throttle.updated_at = now
        if throttle.failure_count >= self.settings.login_max_failures:
            throttle.locked_until = now + timedelta(seconds=self.settings.login_lock_seconds)
        self.repository.add_audit(
            event_type="user.login_failed",
            actor_user_id=user_id,
            request_id=request_id,
            target_type="authentication",
            metadata={"outcome": "invalid_credentials"},
        )
        self.db.commit()
        get_logger().warning(
            "user.login_failed", event_name="user.login_failed", outcome="invalid_credentials"
        )

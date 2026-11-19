"""Administrator authentication: Argon2id hashing, server-side sessions, CSRF tokens, login throttling."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select, update

from app.db.models import AdminSession, AdminUser
from app.db.session import Database, utcnow

# Argon2id (argon2-cffi default type) with OWASP-recommended parameters.
_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)
# Verified against when the email is unknown, so response time doesn't reveal which emails exist.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))

MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def normalise_email(email: str) -> str:
    return email.strip().lower()


def validate_new_password(password: str) -> list[str]:
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"must be at least {MIN_PASSWORD_LENGTH} characters")
    if password.strip() != password:
        problems.append("must not start or end with spaces")
    return problems


@dataclass
class SessionInfo:
    admin_id: int
    email: str
    expires_at: datetime
    session_id: int
    csrf_hash: str


@dataclass
class NewSession:
    token: str
    csrf_token: str
    expires_at: datetime


class AuthService:
    def __init__(self, db: Database, ttl_minutes: int, idle_minutes: int) -> None:
        self.db = db
        self.ttl = timedelta(minutes=ttl_minutes)
        self.idle = timedelta(minutes=idle_minutes)

    # --------------------------------------------------------------- admins
    def create_or_reset_admin(self, email: str, password: str, *, reset: bool = False) -> str:
        email = normalise_email(email)
        problems = validate_new_password(password)
        if problems:
            raise ValueError("Password " + "; ".join(problems) + ".")
        now = utcnow()
        with self.db.session() as s:
            user = s.scalar(select(AdminUser).where(AdminUser.email == email))
            if user and not reset:
                raise ValueError(f"Administrator {email} already exists (use --reset-password to change it).")
            if user is None:
                s.add(AdminUser(email=email, password_hash=hash_password(password), is_active=True,
                                created_at=now, password_changed_at=now))
                return "created"
            user.password_hash = hash_password(password)
            user.password_changed_at = now
            user.is_active = True
            # Revoke all existing sessions after a password change.
            s.execute(update(AdminSession).where(AdminSession.admin_id == user.id, AdminSession.revoked_at.is_(None))
                      .values(revoked_at=now))
            return "reset"

    def authenticate(self, email: str, password: str) -> AdminUser | None:
        email = normalise_email(email)
        with self.db.session() as s:
            user = s.scalar(select(AdminUser).where(AdminUser.email == email))
            if user is None or not user.is_active:
                verify_password(_DUMMY_HASH, password)  # equalise timing
                return None
            if not verify_password(user.password_hash, password):
                return None
            if _hasher.check_needs_rehash(user.password_hash):
                user.password_hash = hash_password(password)
            user.last_login_at = utcnow()
            return user

    # ------------------------------------------------------------- sessions
    def create_session(self, admin_id: int) -> NewSession:
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = utcnow()
        expires = now + self.ttl
        with self.db.session() as s:
            s.add(AdminSession(token_hash=_sha256(token), csrf_hash=_sha256(csrf), admin_id=admin_id,
                               created_at=now, last_seen_at=now, expires_at=expires))
        return NewSession(token=token, csrf_token=csrf, expires_at=expires)

    def validate_session(self, token: str | None, *, touch: bool = True) -> SessionInfo | None:
        if not token or len(token) > 200:
            return None
        now = utcnow()
        with self.db.session() as s:
            row = s.scalar(select(AdminSession).where(AdminSession.token_hash == _sha256(token)))
            if row is None or row.revoked_at is not None or row.expires_at <= now or now - row.last_seen_at > self.idle:
                return None
            user = s.get(AdminUser, row.admin_id)
            if user is None or not user.is_active or user.password_changed_at > row.created_at:
                return None
            if touch:
                row.last_seen_at = now
            return SessionInfo(admin_id=user.id, email=user.email, expires_at=row.expires_at, session_id=row.id,
                               csrf_hash=row.csrf_hash)

    @staticmethod
    def check_csrf(info: SessionInfo, csrf_token: str | None) -> bool:
        return bool(csrf_token) and hmac.compare_digest(info.csrf_hash, _sha256(csrf_token or ""))

    def revoke(self, session_id: int) -> None:
        with self.db.session() as s:
            row = s.get(AdminSession, session_id)
            if row and row.revoked_at is None:
                row.revoked_at = utcnow()


class LoginThrottle:
    """Failed-login limiter keyed by (client IP) and (email, IP). In-process."""

    def __init__(self, max_failures: int, window_minutes: int) -> None:
        self.max_failures = max_failures
        self.window = window_minutes * 60
        self._fail: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._fail[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def blocked(self, ip: str, email: str) -> int:
        """Seconds until the caller may retry (0 = allowed)."""
        now = time.monotonic()
        with self._lock:
            waits = []
            for key, limit in ((f"ip:{ip}", self.max_failures * 4), (f"acct:{normalise_email(email)}|{ip}", self.max_failures)):
                q = self._prune(key, now)
                if len(q) >= limit:
                    waits.append(int(self.window - (now - q[0])) + 1)
            return max(waits, default=0)

    def failure(self, ip: str, email: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._fail[f"ip:{ip}"].append(now)
            self._fail[f"acct:{normalise_email(email)}|{ip}"].append(now)

    def success(self, ip: str, email: str) -> None:
        with self._lock:
            self._fail.pop(f"acct:{normalise_email(email)}|{ip}", None)

"""Security helpers: audit logging, rate limiting, and lockout state."""

import logging
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from .models import AuditEvent, LoginAttempt

logger = logging.getLogger(__name__)

MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION = timedelta(minutes=15)
REGISTER_LIMIT = 5
REGISTER_WINDOW_SECONDS = 60 * 60


def client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def log_event(request, action, user=None, **metadata):
    """Best-effort audit logging that never breaks the user flow."""
    if user is None:
        candidate = getattr(request, 'user', None)
        if candidate is not None and candidate.is_authenticated:
            user = candidate
    try:
        return AuditEvent.objects.create(
            user=user,
            action=action,
            ip_address=client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:2000],
            metadata=metadata,
        )
    except Exception:
        logger.exception('Unable to write audit event %s', action)
        return None


def get_lock_state(username, ip_address):
    """Return seconds remaining if locked, otherwise None."""
    attempt = LoginAttempt.objects.filter(
        username__iexact=username.strip(),
        ip_address=ip_address,
    ).first()
    if attempt is None or attempt.locked_until is None:
        return None
    if timezone.now() >= attempt.locked_until:
        attempt.delete()
        return None
    return max(int((attempt.locked_until - timezone.now()).total_seconds()), 1)


def register_failure(username, ip_address):
    """Increment the failure count and lock after the threshold."""
    attempt, _ = LoginAttempt.objects.get_or_create(
        username=username.strip(),
        ip_address=ip_address,
    )
    attempt.failed_attempts += 1
    if attempt.failed_attempts >= MAX_FAILED_ATTEMPTS:
        attempt.locked_until = timezone.now() + LOCK_DURATION
    attempt.save(update_fields=['failed_attempts', 'locked_until', 'last_attempt_at'])
    if attempt.locked_until:
        return 0
    return MAX_FAILED_ATTEMPTS - attempt.failed_attempts


def clear_failures(username, ip_address):
    LoginAttempt.objects.filter(
        username__iexact=username.strip(),
        ip_address=ip_address,
    ).delete()


def rate_limit_exceeded(bucket, key, limit, window_seconds):
    """Simple fixed-window cache rate limiter. Returns True when blocked."""
    cache_key = f'ratelimit:{bucket}:{key}'
    added = cache.add(cache_key, 1, timeout=window_seconds)
    if added:
        return False
    try:
        count = cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, timeout=window_seconds)
        return False
    return count > limit


def registration_allowed(ip_address):
    if not ip_address:
        return True
    return not rate_limit_exceeded(
        'register', ip_address, REGISTER_LIMIT, REGISTER_WINDOW_SECONDS,
    )

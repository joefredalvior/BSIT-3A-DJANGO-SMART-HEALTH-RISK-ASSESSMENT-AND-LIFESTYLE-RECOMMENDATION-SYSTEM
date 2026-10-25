"""Session lifetime helpers and authentication timestamp bookkeeping."""

from django.conf import settings
from django.utils import timezone

SESSION_STARTED_KEY = 'auth_started_at'
SESSION_ACTIVITY_KEY = 'auth_last_activity'


def mark_session_authenticated(request):
    now = timezone.now().timestamp()
    request.session[SESSION_STARTED_KEY] = now
    request.session[SESSION_ACTIVITY_KEY] = now


def session_timeout_reason(request):
    if not request.user.is_authenticated:
        return None

    now = timezone.now().timestamp()
    started = request.session.get(SESSION_STARTED_KEY)
    last_activity = request.session.get(SESSION_ACTIVITY_KEY)
    if started is None or last_activity is None:
        mark_session_authenticated(request)
        return None

    idle_limit = getattr(settings, 'SESSION_IDLE_TIMEOUT_SECONDS', 1800)
    absolute_limit = getattr(settings, 'SESSION_ABSOLUTE_TIMEOUT_SECONDS', 43200)
    if idle_limit and now - last_activity >= idle_limit:
        return 'idle'
    if absolute_limit and now - started >= absolute_limit:
        return 'absolute'

    refresh_after = getattr(settings, 'SESSION_ACTIVITY_REFRESH_SECONDS', 60)
    if refresh_after and now - last_activity >= refresh_after:
        request.session[SESSION_ACTIVITY_KEY] = now
    return None

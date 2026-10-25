from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import redirect

from .http import wants_json
from .models import UserSession
from .security import log_event
from .session_security import session_timeout_reason


SESSION_TRACK_CACHE_SECONDS = 60


class ActiveSessionMiddleware:
    """Keep a small, user-facing record of active sessions."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            if not request.session.session_key:
                request.session.save()
            key = request.session.session_key
            cache_key = f'session-tracked:{key}'
            if cache.get(cache_key) is None:
                UserSession.objects.update_or_create(
                    session_key=key,
                    defaults={
                        'user': request.user,
                        'ip_address': request.META.get('REMOTE_ADDR'),
                        'user_agent': request.META.get('HTTP_USER_AGENT', '')[:240],
                        'ended_at': None,
                    },
                )
                cache.set(cache_key, True, SESSION_TRACK_CACHE_SECONDS)
            request.current_session_key = key
        return self.get_response(request)


class SessionTimeoutMiddleware:
    """Expire idle and over-age authenticated sessions."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(('/static/', '/media/')):
            return self.get_response(request)

        reason = session_timeout_reason(request)
        if reason is not None:
            log_event(request, f'session.{reason}_timeout')
            logout(request)
            if wants_json(request):
                return JsonResponse(
                    {'error': 'Your session expired. Sign in again to continue.'},
                    status=401,
                )
            messages.warning(request, 'Your session expired. Please sign in again.')
            return redirect(settings.LOGIN_URL)
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """Apply conservative browser security headers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        csp = getattr(settings, 'CONTENT_SECURITY_POLICY', '')
        if csp and not response.has_header('Content-Security-Policy'):
            response['Content-Security-Policy'] = csp
        if not response.has_header('Permissions-Policy'):
            response['Permissions-Policy'] = (
                'camera=(), microphone=(), geolocation=(), payment=()'
            )
        if not response.has_header('Cross-Origin-Opener-Policy'):
            response['Cross-Origin-Opener-Policy'] = 'same-origin'
        if not response.has_header('Cross-Origin-Resource-Policy'):
            response['Cross-Origin-Resource-Policy'] = 'same-origin'
        if not response.has_header('X-Permitted-Cross-Domain-Policies'):
            response['X-Permitted-Cross-Domain-Policies'] = 'none'

        if request.user.is_authenticated:
            content_type = response.get('Content-Type', '')
            if content_type.startswith(('text/html', 'application/json')):
                response['Cache-Control'] = 'no-store, private'
                response['Pragma'] = 'no-cache'
        return response

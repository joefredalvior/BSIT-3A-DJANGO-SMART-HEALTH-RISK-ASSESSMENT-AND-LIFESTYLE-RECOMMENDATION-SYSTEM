"""Custom CSRF failure response with audit logging."""

from django.http import JsonResponse
from django.shortcuts import render

from .http import wants_json
from .security import log_event


def csrf_failure(request, reason=''):
    log_event(request, 'security.csrf_failure', reason=str(reason)[:240])
    if wants_json(request):
        return JsonResponse(
            {'error': 'Security verification failed. Refresh the page and try again.'},
            status=403,
        )
    return render(request, '403_csrf.html', {'reason': reason}, status=403)

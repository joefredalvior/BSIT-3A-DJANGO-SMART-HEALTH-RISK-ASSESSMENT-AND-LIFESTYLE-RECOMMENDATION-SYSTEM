"""Transactional email helpers."""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

from .tokens import make_verification_token

logger = logging.getLogger(__name__)


def send_verification_email(request, user):
    token = make_verification_token(user)
    path = reverse('verify_email', args=[token])
    url = request.build_absolute_uri(path) if request else path
    subject = 'Verify your HealthWise email address'
    body = (
        f'Hello {user.first_name or user.username},\n\n'
        'Please confirm your email address so we can keep your account secure '
        'and send you important health report updates.\n\n'
        f'{url}\n\n'
        'This link expires in 3 days. If you did not create a HealthWise '
        'account, you can safely ignore this email.\n'
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
        return True
    except Exception:
        logger.exception('Could not send verification email to %s', user.pk)
        return False

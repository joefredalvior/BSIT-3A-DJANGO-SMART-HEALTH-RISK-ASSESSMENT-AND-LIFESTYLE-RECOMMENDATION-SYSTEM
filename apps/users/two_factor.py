import secrets

import pyotp
from django.utils import timezone

from .models import UserTwoFactor


def get_settings(user):
    settings_obj, _ = UserTwoFactor.objects.get_or_create(user=user)
    return settings_obj


def start_setup(user):
    settings_obj = get_settings(user)
    settings_obj.secret = pyotp.random_base32()
    settings_obj.enabled = False
    settings_obj.backup_codes = []
    settings_obj.save(update_fields=['secret', 'enabled', 'backup_codes'])
    return settings_obj


def provisioning_uri(user, secret):
    issuer = 'HealthWise'
    return pyotp.TOTP(secret).provisioning_uri(
        name=user.get_username(), issuer_name=issuer,
    )


def verify_code(secret, code):
    if not secret or not code:
        return False
    return pyotp.TOTP(secret).verify(str(code).strip(), valid_window=1)


def generate_backup_codes(count=8):
    return [secrets.token_hex(4) for _ in range(count)]


def consume_backup_code(settings_obj, code):
    value = str(code).strip().lower()
    for candidate in list(settings_obj.backup_codes):
        if secrets.compare_digest(candidate.lower(), value):
            remaining = [item for item in settings_obj.backup_codes if item != candidate]
            settings_obj.backup_codes = remaining
            settings_obj.save(update_fields=['backup_codes'])
            return True
    return False


def confirm(settings_obj):
    settings_obj.enabled = True
    settings_obj.confirmed_at = timezone.now()
    settings_obj.backup_codes = generate_backup_codes()
    settings_obj.save(update_fields=['enabled', 'confirmed_at', 'backup_codes'])
    return settings_obj


def disable(settings_obj):
    settings_obj.enabled = False
    settings_obj.secret = ''
    settings_obj.backup_codes = []
    settings_obj.save(update_fields=['enabled', 'secret', 'backup_codes'])

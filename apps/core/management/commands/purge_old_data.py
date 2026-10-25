from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import AuditEvent, LoginAttempt, UserSession
from apps.health.models import ReportShare
from apps.wellness.models import SecureMessage


class Command(BaseCommand):
    help = 'Delete old audit, login, session, share and message records.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        now = timezone.now()
        audit_days = getattr(settings, 'AUDIT_RETENTION_DAYS', 365)
        login_days = getattr(settings, 'LOGIN_RETENTION_DAYS', 90)
        message_days = getattr(settings, 'MESSAGE_RETENTION_DAYS', 730)
        dry_run = options['dry_run']

        targets = [
            (AuditEvent.objects.filter(created_at__lt=now - timedelta(days=audit_days)), 'audit events'),
            (LoginAttempt.objects.filter(last_attempt_at__lt=now - timedelta(days=login_days)), 'login attempts'),
            (Session.objects.filter(expire_date__lt=now), 'expired sessions'),
            (UserSession.objects.filter(ended_at__lt=now - timedelta(days=login_days)), 'old tracked sessions'),
            (ReportShare.objects.filter(expires_at__lt=now - timedelta(days=30)), 'expired report shares'),
            (
                SecureMessage.objects.filter(
                    created_at__lt=now - timedelta(days=message_days),
                    read_at__isnull=False,
                ),
                'old read messages',
            ),
        ]

        for queryset, label in targets:
            count = queryset.count()
            if not dry_run:
                queryset.delete()
            prefix = '[dry-run] would delete' if dry_run else 'Deleted'
            self.stdout.write(f'{prefix} {count} {label}.')

        self.stdout.write(self.style.SUCCESS('Retention cleanup complete.'))

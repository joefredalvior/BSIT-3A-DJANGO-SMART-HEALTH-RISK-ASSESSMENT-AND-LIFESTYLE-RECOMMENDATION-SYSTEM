from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from apps.users.models import UserProfile


class Command(BaseCommand):
    help = 'Email verified users who have not completed an assessment recently.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=None)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        days = options['days'] or getattr(settings, 'ACCOUNT_REMINDER_DAYS', 30)
        cutoff = timezone.now() - timedelta(days=days)
        dry_run = options['dry_run']

        profiles = (
            UserProfile.objects
            .select_related('user')
            .filter(
                user__is_active=True,
                reminder_opt_in=True,
                email_verified=True,
            )
            .exclude(user__email='')
        )

        site_url = getattr(settings, 'SITE_URL', 'https://healthwise.local').rstrip('/')
        protocol, domain = site_url.split('://', 1)

        sent = 0
        skipped = 0
        for profile in profiles:
            user = profile.user
            latest = user.assessments.first()
            if latest is None or latest.created_at >= cutoff:
                skipped += 1
                continue
            if profile.last_reminder_sent and profile.last_reminder_sent >= cutoff:
                skipped += 1
                continue

            body = render_to_string('emails/reminder_email.txt', {
                'user': user,
                'last_assessment': latest,
                'protocol': protocol,
                'domain': domain,
            })
            if dry_run:
                self.stdout.write(f'[dry-run] would email {user.username} <{user.email}>')
                sent += 1
                continue

            try:
                send_mail(
                    'Time for your HealthWise check-in',
                    body,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                )
            except Exception as exc:
                self.stderr.write(f'Failed for {user.username}: {exc}')
                continue

            profile.last_reminder_sent = timezone.now()
            profile.save(update_fields=['last_reminder_sent', 'updated_at'])
            sent += 1

        self.stdout.write(self.style.SUCCESS(
            f'Reminders sent: {sent}; skipped: {skipped}'
        ))

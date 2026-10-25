from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from apps.users.models import UserProfile


class Command(BaseCommand):
    help = 'Email a weekly health summary to opted-in, verified users.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options['days'])
        dry_run = options['dry_run']
        site_url = getattr(settings, 'SITE_URL', 'https://healthwise.local').rstrip('/')

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

        sent = 0
        for profile in profiles:
            if profile.last_digest_sent and profile.last_digest_sent >= cutoff:
                continue
            user = profile.user
            latest = user.assessments.first()
            if latest is None:
                continue
            body = render_to_string('emails/weekly_digest.txt', {
                'user': user,
                'latest': latest,
                'goals': user.health_goals.filter(is_active=True)[:5],
                'achievements': user.achievements.all()[:5],
                'site_url': site_url,
            })
            if dry_run:
                self.stdout.write(f'[dry-run] would email {user.username} <{user.email}>')
                sent += 1
                continue
            try:
                send_mail(
                    'Your weekly HealthWise summary',
                    body,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                )
            except Exception as exc:
                self.stderr.write(f'Failed for {user.username}: {exc}')
                continue
            profile.last_digest_sent = timezone.now()
            profile.save(update_fields=['last_digest_sent', 'updated_at'])
            sent += 1

        self.stdout.write(self.style.SUCCESS(f'Digests sent: {sent}'))

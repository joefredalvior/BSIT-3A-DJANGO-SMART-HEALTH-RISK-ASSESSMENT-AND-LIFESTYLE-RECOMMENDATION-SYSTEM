from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.wellness.models import Medication


class Command(BaseCommand):
    help = 'Send SMS medication reminders through the configured SMS backend.'

    def add_arguments(self, parser):
        parser.add_argument('--window', type=int, default=30, help='Minutes after the reminder time.')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        backend = getattr(settings, 'SMS_BACKEND', 'console')
        if backend not in ('console', 'dummy'):
            raise CommandError(
                f'SMS backend "{backend}" is not implemented. Configure SMS_BACKEND=console '
                'or add a provider backend before enabling SMS.'
            )

        now = timezone.localtime()
        window_end = now + timedelta(minutes=options['window'])
        medications = Medication.objects.select_related('user', 'user__profile').filter(
            is_active=True,
            reminder_time__isnull=False,
            user__is_active=True,
            user__profile__sms_opt_in=True,
        ).exclude(user__profile__phone_number='')

        sent = 0
        for medication in medications:
            reminder = medication.reminder_time
            due = now.replace(hour=reminder.hour, minute=reminder.minute, second=0, microsecond=0)
            if not (now - timedelta(minutes=5) <= due <= window_end):
                continue
            if medication.last_reminder_sent == now.date():
                continue
            message = (
                f'HealthWise reminder: time to take {medication.name}'
                f'{(" (" + medication.dosage + ")") if medication.dosage else ""}.'
            )
            if options['dry_run'] or backend == 'console':
                self.stdout.write(f'[sms:{backend}] {medication.user.profile.phone_number}: {message}')
            if not options['dry_run']:
                medication.last_reminder_sent = now.date()
                medication.save(update_fields=['last_reminder_sent', 'updated_at'])
            sent += 1

        self.stdout.write(self.style.SUCCESS(f'SMS reminders processed: {sent}'))

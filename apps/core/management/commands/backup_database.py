import sqlite3
from contextlib import closing
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone


class Command(BaseCommand):
    help = 'Create a timestamped SQLite database backup.'

    def add_arguments(self, parser):
        parser.add_argument('--output', default='backups', help='Backup directory.')

    def handle(self, *args, **options):
        if connection.vendor != 'sqlite':
            raise CommandError('This command currently supports SQLite only.')
        source = Path(settings.DATABASES['default']['NAME'])
        if not source.exists():
            raise CommandError(f'Database not found: {source}')
        destination_dir = Path(options['output'])
        destination_dir.mkdir(parents=True, exist_ok=True)
        stamp = timezone.localtime().strftime('%Y%m%d-%H%M%S')
        destination = destination_dir / f'{source.stem}-{stamp}.sqlite3'

        with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)

        self.stdout.write(self.style.SUCCESS(f'Backup written to {destination}'))

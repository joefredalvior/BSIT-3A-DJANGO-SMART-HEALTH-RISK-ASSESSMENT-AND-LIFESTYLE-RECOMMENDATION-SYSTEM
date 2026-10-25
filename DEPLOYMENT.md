# Deployment checklist

## 1. Environment

Copy `.env.example` to `.env` on the server and set:

```text
DJANGO_SETTINGS_MODULE=mysite.settings_production
DJANGO_SECRET_KEY=<long random value>
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=your-domain.example
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.example
DJANGO_SECURE_COOKIES=1
DJANGO_SECURE_SSL_REDIRECT=1
DJANGO_HSTS_SECONDS=31536000
DJANGO_HSTS_INCLUDE_SUBDOMAINS=1
DJANGO_HSTS_PRELOAD=0
DJANGO_BEHIND_PROXY=1
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.example
SITE_URL=https://your-domain.example

```

Use a database other than SQLite for production:

```text
DB_ENGINE=django.db.backends.mysql
DB_NAME=healthwise
DB_USER=healthwise
DB_PASSWORD=<strong password>
DB_HOST=127.0.0.1
DB_PORT=3306
```

Set email delivery (`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
`EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_TIMEOUT`, `DEFAULT_FROM_EMAIL`).

Production uses the database cache for cross-worker rate limiting. The default
cache table is `healthwise_cache`; override it with `DJANGO_CACHE_LOCATION` if
needed.

Only enable `DJANGO_HSTS_PRELOAD=1` after the domain is fully HTTPS-ready and
you are prepared to submit it to the HSTS preload list.

## 2. Install and build

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createcachetable
python manage.py collectstatic --noinput
python manage.py check --deploy
```

## 3. Run

```bash
gunicorn mysite.wsgi:application --bind 0.0.0.0:8000 --workers 3
```

Put Nginx or another reverse proxy in front for TLS and static files. If
WhiteNoise is installed, it can serve static files directly.

## 4. Verify

- `GET /healthz/` returns `{"status":"ok","database":"ok"}`.
- Register a test account; the verification email arrives.
- Password reset email arrives and the link works.
- Assessment report, export, and reminder emails work.
- `python manage.py check --deploy` reports no errors.

## 5. Operations

- Schedule `python manage.py send_reminders` daily.
- Schedule `python manage.py send_digests` weekly for opted-in users.
- Schedule `python manage.py send_sms_reminders` every 15 minutes only after
  implementing an SMS provider. The default `SMS_BACKEND=console` prints
  messages to the process log and does not contact patients.
- Schedule `python manage.py purge_old_data` monthly. Use `--dry-run` first.
- Back up the database daily with `python manage.py backup_database --output /path/to/backups`
  (SQLite), or use your database provider's backup tooling for MySQL.
- Test database restores regularly.
- Rotate the secret key only with a planned session reset.
- Keep `DEBUG=0`; never serve with the development server.
- Review the staff audit page (`/audit/`) or `/admin/core/auditevent/` for
  suspicious login, export, share, or caregiver activity.

## 6. Feature notes

- Two-factor authentication uses TOTP (`pyotp`) and QR codes (`qrcode`).
  Users can enable it from Profile -> Security & devices.
- Shared report links are read-only, expire after 7 days, and can be revoked
  from the report page.
- PWA install support uses `/manifest.webmanifest` and `/sw.js`; the service
  worker caches static assets only and falls back to `/offline/`. Authenticated
  health pages are intentionally not cached.
- The what-if simulator is an estimate only and never modifies saved records.
- PHQ-9 and GAD-7 screenings are not diagnoses; crisis guidance is shown for
  severe scores.

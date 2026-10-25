import json
import sqlite3
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pyotp
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditEvent, UserSession
from apps.core.session_security import SESSION_ACTIVITY_KEY, SESSION_STARTED_KEY
from apps.health.models import Achievement, Assessment, ReportShare
from apps.health.services import award_achievements
from apps.users.models import UserProfile
from apps.users.two_factor import get_settings

User = get_user_model()


def make_assessment(user, **overrides):
    fields = dict(
        user=user, age=40, sex='male', height_cm=175, weight_kg=80,
        waist_cm=90, systolic=120, diastolic=80, blood_pressure_band='normal',
        activity_level='moderate', smoking_status='never',
        alcohol_status='light', diet_quality='mixed', sleep_hours=7,
        risk_score=30, risk_level='Moderate', bmi=26.1,
        bmi_category='Overweight', findings=[], recommendations=[], targets=[],
    )
    fields.update(overrides)
    return Assessment.objects.create(**fields)


class TwoFactorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'twofactor', password='Xk9!mQ2#Lp', email='tf@example.com',
        )
        UserProfile.objects.create(user=self.user, email_verified=True)

    def test_login_with_enabled_2fa_requires_challenge(self):
        settings_obj = get_settings(self.user)
        settings_obj.secret = pyotp.random_base32()
        settings_obj.enabled = True
        settings_obj.save(update_fields=['secret', 'enabled'])

        response = self.client.post(reverse('login'), {
            'username': 'twofactor', 'password': 'Xk9!mQ2#Lp',
        })
        self.assertRedirects(response, reverse('two_factor_challenge'))
        self.assertNotIn('_auth_user_id', self.client.session)

        code = pyotp.TOTP(settings_obj.secret).now()
        response = self.client.post(reverse('two_factor_challenge'), {'code': code})
        self.assertRedirects(response, reverse('dashboard'))
        self.assertIn('_auth_user_id', self.client.session)

    def test_setup_renders_qr_and_enabling_generates_backup_codes(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('users:two_factor_setup'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Manual setup key')

        settings_obj = get_settings(self.user)
        code = pyotp.TOTP(settings_obj.secret).now()
        response = self.client.post(reverse('users:two_factor_setup'), {'code': code})
        self.assertEqual(response.status_code, 200)
        settings_obj.refresh_from_db()
        self.assertTrue(settings_obj.enabled)
        self.assertEqual(len(settings_obj.backup_codes), 8)

    def test_invalid_2fa_code_does_not_log_in(self):
        settings_obj = get_settings(self.user)
        settings_obj.secret = pyotp.random_base32()
        settings_obj.enabled = True
        settings_obj.save(update_fields=['secret', 'enabled'])
        self.client.post(reverse('login'), {
            'username': 'twofactor', 'password': 'Xk9!mQ2#Lp',
        })
        response = self.client.post(reverse('two_factor_challenge'), {'code': '000000'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_2fa_disable_requires_password_and_valid_code(self):
        settings_obj = get_settings(self.user)
        settings_obj.secret = pyotp.random_base32()
        settings_obj.enabled = True
        settings_obj.backup_codes = ['abcd1234']
        settings_obj.save(update_fields=['secret', 'enabled', 'backup_codes'])
        self.client.force_login(self.user)

        response = self.client.post(reverse('users:two_factor_disable'), {
            'password': 'wrong-password', 'code': 'abcd1234',
        })
        self.assertRedirects(response, reverse('users:two_factor_setup'))
        settings_obj.refresh_from_db()
        self.assertTrue(settings_obj.enabled)

        code = pyotp.TOTP(settings_obj.secret).now()
        response = self.client.post(reverse('users:two_factor_disable'), {
            'password': 'Xk9!mQ2#Lp', 'code': code,
        })
        self.assertRedirects(
            response, reverse('users:two_factor_setup'),
            fetch_redirect_response=False,
        )
        settings_obj.refresh_from_db()
        self.assertFalse(settings_obj.enabled)
        self.assertEqual(settings_obj.secret, '')
        self.assertEqual(settings_obj.backup_codes, [])



class LanguageAndAuditTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('auditor', password='pass', is_staff=True)
        self.patient = User.objects.create_user('languageuser', password='pass')

    def test_language_switch_is_stored_in_session(self):
        self.client.force_login(self.patient)
        response = self.client.get(
            reverse('set_language', args=['fil']), {'next': reverse('dashboard')},
        )
        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(self.client.session['ui_language'], 'fil')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Aking mga Layunin')

    def test_language_switch_rejects_external_redirect(self):
        self.client.force_login(self.patient)
        response = self.client.get(
            reverse('set_language', args=['fil']), {'next': 'https://example.com/phish'},
        )
        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(self.client.session['ui_language'], 'fil')

    def test_audit_log_ignores_invalid_dates(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('audit_log'), {'from': 'not-a-date', 'to': 'bad'})
        self.assertEqual(response.status_code, 200)

    def test_patient_cannot_view_audit_log(self):
        self.client.force_login(self.patient)
        response = self.client.get(reverse('audit_log'))
        self.assertEqual(response.status_code, 302)

    def test_staff_can_view_and_export_audit_log(self):
        AuditEvent.objects.create(action='test.event', ip_address='127.0.0.1', metadata={'ok': True})
        self.client.force_login(self.staff)
        response = self.client.get(reverse('audit_log'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'test.event')
        response = self.client.get(reverse('audit_log_export'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')

    def test_pwa_routes_are_public(self):
        self.assertEqual(self.client.get(reverse('manifest')).status_code, 200)
        self.assertEqual(self.client.get(reverse('service_worker')).status_code, 200)
        self.assertEqual(self.client.get(reverse('offline')).status_code, 200)


class ReportShareTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('sharer', password='pass')
        self.other = User.objects.create_user('viewer', password='pass')
        self.record = make_assessment(self.user)
        self.client.force_login(self.user)

    def test_create_and_view_share_link(self):
        response = self.client.post(reverse('health:share_report', args=[self.record.pk]))
        self.assertRedirects(response, reverse('health:report', args=[self.record.pk]))
        share = ReportShare.objects.get(assessment=self.record)
        self.assertTrue(share.is_valid)

        self.client.logout()
        response = self.client.get(reverse('health:shared_report', args=[share.token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Shared health risk report')
        share.refresh_from_db()
        self.assertEqual(share.view_count, 1)

    def test_revoked_share_returns_gone(self):
        share = ReportShare.objects.create(
            assessment=self.record, created_by=self.user,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.post(reverse('health:revoke_share', args=[share.pk]))
        self.client.logout()
        response = self.client.get(reverse('health:shared_report', args=[share.token]))
        self.assertEqual(response.status_code, 410)

    def test_other_users_cannot_create_share(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse('health:share_report', args=[self.record.pk]))
        self.assertEqual(response.status_code, 404)

    def test_simulator_returns_estimated_score(self):
        response = self.client.post(
            reverse('health:simulate'),
            data=json.dumps({'assessment': self.record.pk, 'weight_kg': 70}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('score', payload)
        self.assertIn('delta', payload)

    def test_achievements_are_awarded(self):
        make_assessment(self.user)
        award_achievements(self.user)
        self.assertTrue(Achievement.objects.filter(user=self.user, code='first_assessment').exists())


class SecurityMiddlewareTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('secure-user', password='Xk9!mQ2#Lp')

    def test_authenticated_pages_have_security_headers(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertIn("default-src 'self'", response['Content-Security-Policy'])
        self.assertIn('camera=()', response['Permissions-Policy'])
        self.assertEqual(response['Cross-Origin-Opener-Policy'], 'same-origin')
        self.assertIn('no-store', response['Cache-Control'])

    def test_csrf_rejects_post_without_token(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse('login'), {
            'username': 'secure-user', 'password': 'Xk9!mQ2#Lp',
        })
        self.assertEqual(response.status_code, 403)
        self.assertTrue(AuditEvent.objects.filter(action='security.csrf_failure').exists())

    def test_csrf_accepts_post_with_token(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse('login'))
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = client.post(reverse('login'), {
            'username': 'secure-user',
            'password': 'Xk9!mQ2#Lp',
            'csrfmiddlewaretoken': token,
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertIn('_auth_user_id', client.session)

    @override_settings(SESSION_IDLE_TIMEOUT_SECONDS=60)
    def test_idle_session_is_logged_out(self):
        self.client.force_login(self.user)
        self.client.get(reverse('dashboard'))
        session = self.client.session
        session[SESSION_ACTIVITY_KEY] = timezone.now().timestamp() - 120
        session.save()

        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(
            response, reverse('login'), fetch_redirect_response=False,
        )
        self.assertNotIn('_auth_user_id', self.client.session)

    @override_settings(SESSION_ABSOLUTE_TIMEOUT_SECONDS=60)
    def test_absolute_session_age_is_enforced(self):
        self.client.force_login(self.user)
        self.client.get(reverse('dashboard'))
        session = self.client.session
        session[SESSION_STARTED_KEY] = timezone.now().timestamp() - 120
        session.save()

        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(
            response, reverse('login'), fetch_redirect_response=False,
        )
        self.assertNotIn('_auth_user_id', self.client.session)


class SessionManagementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('session-user', password='pass')

    def test_patient_can_revoke_another_session(self):
        second_client = Client()
        self.client.force_login(self.user)
        self.client.get(reverse('dashboard'))
        second_client.force_login(self.user)
        second_client.get(reverse('dashboard'))

        tracked = UserSession.objects.get(
            user=self.user, session_key=second_client.session.session_key,
        )
        current_key = self.client.session.session_key
        response = self.client.post(
            reverse('users:end_session', args=[tracked.pk]),
        )
        self.assertRedirects(response, reverse('users:security'))
        tracked.refresh_from_db()
        self.assertIsNotNone(tracked.ended_at)
        self.assertEqual(second_client.get(reverse('dashboard')).status_code, 302)
        self.assertTrue(UserSession.objects.filter(
            user=self.user, session_key=current_key, ended_at__isnull=True,
        ).exists())

    def test_patient_cannot_revoke_another_users_session(self):
        other = User.objects.create_user('other-session-user', password='pass')
        self.client.force_login(self.user)
        self.client.get(reverse('dashboard'))
        other_client = Client()
        other_client.force_login(other)
        other_client.get(reverse('dashboard'))
        tracked = UserSession.objects.get(
            user=other, session_key=other_client.session.session_key,
        )
        response = self.client.post(
            reverse('users:end_session', args=[tracked.pk]),
        )
        self.assertEqual(response.status_code, 404)


class BackupCommandTests(TestCase):
    def test_backup_creates_sqlite_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.sqlite3'
            connection = sqlite3.connect(source)
            try:
                connection.execute('CREATE TABLE sample (id INTEGER PRIMARY KEY)')
                connection.execute('INSERT INTO sample DEFAULT VALUES')
                connection.commit()
            finally:
                connection.close()
            destination = Path(tmp) / 'backups'

            with patch.dict(settings.DATABASES['default'], {'NAME': str(source)}):
                call_command('backup_database', output=str(destination), verbosity=0)

            backups = list(destination.glob('*.sqlite3'))
            self.assertEqual(len(backups), 1)
            copied = sqlite3.connect(backups[0])
            try:
                row = copied.execute('SELECT COUNT(*) FROM sample').fetchone()
            finally:
                copied.close()
            self.assertEqual(row[0], 1)


class ThemeDefaultsTests(TestCase):
    def test_theme_settings_are_removed(self):
        staff = User.objects.create_user('theme-admin', password='pass', is_staff=True)
        self.client.force_login(staff)
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, 'Theme Settings')
        self.assertNotContains(response, 'offcanvasSettings')
        self.assertContains(response, 'data-bs-theme-primary="teal"')
        self.assertNotContains(response, 'tabler-theme.js')


class PlannerTests(TestCase):
    def test_plan_contains_meals_and_activity(self):
        from apps.health.planner import build_plan
        user = User.objects.create_user('planner', password='pass')
        record = make_assessment(user, bmi=31.0, bmi_category='Obesity class I', conditions='hypertension')
        plan = build_plan(record)
        self.assertEqual(len(plan['meals']), 4)
        self.assertGreater(plan['activity']['weekly_minutes'], 0)
        self.assertIn('clinician', plan['note'])


class ScheduledCommandTests(TestCase):
    def setUp(self):
        from django.core.management import call_command
        self.call_command = call_command
        self.user = User.objects.create_user(
            'digestuser', password='pass', email='digest@example.com',
        )
        self.profile = UserProfile.objects.create(
            user=self.user, email_verified=True, reminder_opt_in=True,
        )
        make_assessment(self.user)

    def test_digest_command_sends_and_records_timestamp(self):
        self.call_command('send_digests', verbosity=0)
        self.assertEqual(len(mail.outbox), 1)
        self.profile.refresh_from_db()
        self.assertIsNotNone(self.profile.last_digest_sent)

    def test_sms_command_marks_medication_reminder_sent(self):
        from apps.wellness.models import Medication
        self.profile.phone_number = '+639000000000'
        self.profile.sms_opt_in = True
        self.profile.save(update_fields=['phone_number', 'sms_opt_in'])
        medication = Medication.objects.create(
            user=self.user, name='Test medicine', reminder_time=timezone.localtime().time(),
        )
        self.call_command('send_sms_reminders', verbosity=0)
        medication.refresh_from_db()
        self.assertEqual(medication.last_reminder_sent, timezone.localdate())

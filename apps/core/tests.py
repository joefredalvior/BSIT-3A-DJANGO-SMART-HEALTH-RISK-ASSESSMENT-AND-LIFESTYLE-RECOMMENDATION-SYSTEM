import json

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.core.models import AuditEvent
from apps.core.tokens import make_verification_token
from apps.users.models import UserProfile

User = get_user_model()


class HomeViewTests(TestCase):
    def test_home_renders_for_authenticated_user(self):
        user = User.objects.create_user(username='admin', password='secret1234')

        self.client.force_login(user)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')

    def test_home_requires_login(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 302)


class RegistrationTests(TestCase):
    data = {
        'username': 'newpatient',
        'first_name': 'New',
        'last_name': 'Patient',
        'email': 'newpatient@example.com',
        'password': 'Xk9!mQ2#Lp',
        'confirm_password': 'Xk9!mQ2#Lp',
        'consent': 'on',
    }

    def test_register_page_renders(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Create your account')

    def test_register_creates_user_and_logs_in(self):
        response = self.client.post(reverse('register'), self.data)
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(User.objects.filter(username='newpatient').exists())

        home = self.client.get(reverse('dashboard'))
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, 'Welcome back')

    def test_register_rejects_duplicate_username(self):
        User.objects.create_user('newpatient', password='secret1234')
        response = self.client.post(reverse('register'), self.data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Username already taken')

    def test_register_rejects_mismatched_passwords(self):
        payload = dict(self.data, confirm_password='different123')
        response = self.client.post(reverse('register'), payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Passwords do not match')


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('loginuser', password='Xk9!mQ2#Lp')

    def test_login_page_renders_with_register_link(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('register'))

    def test_login_success_redirects_to_dashboard(self):
        response = self.client.post(reverse('login'), {
            'username': 'loginuser',
            'password': 'Xk9!mQ2#Lp',
        })
        self.assertRedirects(response, reverse('dashboard'))

    def test_login_failure_shows_invalid_message(self):
        response = self.client.post(reverse('login'), {
            'username': 'loginuser',
            'password': 'wrong-password',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid username or password')

    def test_five_failures_locks_the_session(self):
        for _ in range(5):
            self.client.post(reverse('login'), {
                'username': 'loginuser',
                'password': 'wrong-password',
            })

        response = self.client.post(reverse('login'), {
            'username': 'loginuser',
            'password': 'Xk9!mQ2#Lp',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Too many failed attempts')


class EmailVerificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'verifyuser', password='Xk9!mQ2#Lp', email='verify@example.com',
        )
        self.profile = UserProfile.objects.create(user=self.user)

    def test_valid_token_marks_email_verified(self):
        token = make_verification_token(self.user)
        response = self.client.get(reverse('verify_email', args=[token]))

        self.assertRedirects(response, reverse('login'))
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.email_verified)
        self.assertIsNotNone(self.profile.email_verified_at)

    def test_invalid_token_returns_400(self):
        response = self.client.get(reverse('verify_email', args=['not-a-token']))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'invalid or has expired', status_code=400)

    def test_verification_token_is_not_valid_for_another_account(self):
        other = User.objects.create_user(
            'otheruser', password='Xk9!mQ2#Lp', email='other@example.com',
        )
        token = make_verification_token(other)
        other.email = 'changed@example.com'
        other.save(update_fields=['email'])
        response = self.client.get(reverse('verify_email', args=[token]))
        self.assertEqual(response.status_code, 400)


class AccountLifecycleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'accountuser', password='Xk9!mQ2#Lp', email='account@example.com',
        )
        UserProfile.objects.create(
            user=self.user, email_verified=True, reminder_opt_in=True,
        )
        self.client.force_login(self.user)

    def test_account_export_returns_json_attachment(self):
        response = self.client.get(reverse('account_export'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('attachment', response['Content-Disposition'])
        payload = json.loads(response.content)
        self.assertEqual(payload['account']['username'], 'accountuser')

    def test_account_delete_requires_correct_password(self):
        response = self.client.post(
            reverse('account_delete'), {'password': 'wrong-password'},
        )
        self.assertRedirects(response, reverse('users:profile'))
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_account_delete_removes_account(self):
        response = self.client.post(
            reverse('account_delete'), {'password': 'Xk9!mQ2#Lp'},
        )
        self.assertRedirects(response, reverse('login'))
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_privacy_page_renders(self):
        response = self.client.get(reverse('privacy'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Privacy')


class HealthCheckTests(TestCase):
    def test_healthz_returns_json_ok(self):
        response = self.client.get(reverse('healthz'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')


class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'resetuser', password='Xk9!mQ2#Lp', email='reset@example.com',
        )

    def test_password_reset_sends_email(self):
        response = self.client.post(
            reverse('password_reset'), {'email': 'reset@example.com'},
        )
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('reset', mail.outbox[0].body.lower())


class AuditLogTests(TestCase):
    def test_successful_login_is_logged(self):
        User.objects.create_user('audituser', password='Xk9!mQ2#Lp')
        self.client.post(reverse('login'), {
            'username': 'audituser', 'password': 'Xk9!mQ2#Lp',
        })
        self.assertTrue(
            AuditEvent.objects.filter(action='login.success').exists()
        )

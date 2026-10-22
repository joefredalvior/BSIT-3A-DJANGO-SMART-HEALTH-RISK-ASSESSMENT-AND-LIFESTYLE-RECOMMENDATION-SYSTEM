from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

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

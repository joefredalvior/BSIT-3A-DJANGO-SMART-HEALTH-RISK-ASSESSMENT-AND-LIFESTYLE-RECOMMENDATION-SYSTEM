from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.health.models import Assessment
from apps.users.models import UserProfile
from apps.wellness import mental_health
from apps.wellness.models import (
    Appointment,
    CaregiverLink,
    Clinic,
    Medication,
    MentalHealthScreening,
    ReportFeedback,
    SecureMessage,
    VitalReading,
)

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


class WellnessPageTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(
            'wellnesspatient', password='pass', email='patient@example.com',
        )
        UserProfile.objects.create(user=self.patient, email_verified=True)
        self.staff = User.objects.create_user(
            'wellnessstaff', password='pass', is_staff=True,
        )
        self.record = make_assessment(self.patient)
        self.client.force_login(self.patient)

    def test_patient_pages_render(self):
        names = [
            'wellness:vitals', 'wellness:appointments', 'wellness:inbox',
            'wellness:compose_message', 'wellness:screenings',
            'wellness:medications', 'wellness:clinics', 'wellness:caregivers',
            'wellness:caregiver_dashboard', 'wellness:achievements',
            'users:security', 'users:two_factor_setup',
        ]
        for name in names:
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)

    def test_clinician_pages_render(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('wellness:clinician_appointments')).status_code, 200)
        self.assertEqual(self.client.get(reverse('audit_log')).status_code, 200)

    def test_vital_can_be_created_and_deleted(self):
        response = self.client.post(reverse('wellness:vitals'), {
            'measured_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
            'weight_kg': '78.5', 'waist_cm': '88', 'systolic': '118',
            'diastolic': '76', 'sleep_hours': '7.5', 'exercise_minutes': '30',
            'note': 'Morning reading',
        })
        self.assertRedirects(response, reverse('wellness:vitals'))
        reading = VitalReading.objects.get(user=self.patient)
        self.assertEqual(reading.weight_kg, 78.5)
        response = self.client.post(reverse('wellness:delete_vital', args=[reading.pk]))
        self.assertRedirects(response, reverse('wellness:vitals'))
        self.assertFalse(VitalReading.objects.filter(pk=reading.pk).exists())

    def test_csv_import_creates_readings(self):
        upload = SimpleUploadedFile(
            'vitals.csv',
            b'date,weight_kg,systolic,diastolic,sleep_hours\n2026-10-01,77.5,120,78,7\n',
            content_type='text/csv',
        )
        response = self.client.post(reverse('wellness:import_vitals'), {'file': upload})
        self.assertRedirects(response, reverse('wellness:vitals'))
        reading = VitalReading.objects.get(user=self.patient)
        self.assertEqual(reading.source, 'import')
        self.assertEqual(reading.systolic, 120)

    def test_appointment_can_be_requested_and_cancelled(self):
        response = self.client.post(reverse('wellness:appointments'), {
            'clinician': self.staff.pk,
            'scheduled_for': (timezone.localtime() + timedelta(days=3)).strftime('%Y-%m-%dT%H:%M'),
            'duration_minutes': '30',
            'reason': 'Blood pressure review',
        })
        self.assertRedirects(response, reverse('wellness:appointments'))
        appointment = Appointment.objects.get(patient=self.patient)
        self.assertEqual(appointment.status, 'requested')

        self.client.force_login(self.staff)
        response = self.client.post(reverse('wellness:clinician_appointments'), {
            'appointment_id': appointment.pk, 'status': 'confirmed', 'notes': 'Confirmed',
        })
        self.assertRedirects(response, reverse('wellness:clinician_appointments'))
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, 'confirmed')

        self.client.force_login(self.patient)
        response = self.client.post(reverse('wellness:cancel_appointment', args=[appointment.pk]))
        self.assertRedirects(response, reverse('wellness:appointments'))
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, 'cancelled')

    def test_secure_message_and_reply(self):
        response = self.client.post(reverse('wellness:compose_message'), {
            'recipient': self.staff.pk,
            'subject': 'Question',
            'body': 'Is my blood pressure okay?',
        })
        self.assertRedirects(response, reverse('wellness:inbox'))
        message = SecureMessage.objects.get(sender=self.patient)

        self.client.force_login(self.staff)
        response = self.client.get(reverse('wellness:message_detail', args=[message.pk]))
        self.assertEqual(response.status_code, 200)
        message.refresh_from_db()
        self.assertIsNotNone(message.read_at)

        response = self.client.post(reverse('wellness:reply_message', args=[message.pk]), {
            'body': 'Please book a check-up.',
        })
        self.assertRedirects(response, reverse('wellness:message_detail', args=[message.pk]))
        self.assertEqual(SecureMessage.objects.filter(sender=self.staff).count(), 1)

    def test_screening_scores_and_displays_guidance(self):
        answers = ['0'] * len(mental_health.PHQ9_QUESTIONS)
        response = self.client.post(reverse('wellness:screenings'), {
            'kind': 'phq9', 'answer': answers,
        })
        screening = MentalHealthScreening.objects.get(user=self.patient)
        self.assertRedirects(response, reverse('wellness:screening_detail', args=[screening.pk]))
        self.assertEqual(screening.score, 0)
        self.assertEqual(screening.severity, 'minimal')
        response = self.client.get(reverse('wellness:screening_detail', args=[screening.pk]))
        self.assertContains(response, 'Guidance')

    def test_medication_can_be_added_and_paused(self):
        response = self.client.post(reverse('wellness:medications'), {
            'name': 'Amlodipine', 'dosage': '5 mg', 'frequency': 'once daily',
            'start_date': '2026-10-01', 'reminder_time': '08:00', 'is_active': 'on',
        })
        self.assertRedirects(response, reverse('wellness:medications'))
        medication = Medication.objects.get(user=self.patient)
        self.assertTrue(medication.is_active)
        self.client.post(reverse('wellness:toggle_medication', args=[medication.pk]))
        medication.refresh_from_db()
        self.assertFalse(medication.is_active)

    def test_clinic_search_filters_results(self):
        Clinic.objects.create(name='City Health Centre', address='Main Street', services='General')
        Clinic.objects.create(name='Heart Clinic', address='Second Street', services='Cardiology')
        response = self.client.get(reverse('wellness:clinics'), {'q': 'Heart'})
        self.assertContains(response, 'Heart Clinic')
        self.assertNotContains(response, 'City Health Centre')

    def test_report_feedback_is_saved(self):
        response = self.client.post(reverse('wellness:submit_feedback', args=[self.record.pk]), {
            'rating': '5', 'comments': 'Very clear.',
        })
        self.assertRedirects(response, reverse('health:report', args=[self.record.pk]))
        feedback = ReportFeedback.objects.get(assessment=self.record)
        self.assertEqual(feedback.rating, 5)


class CaregiverTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('careowner', password='pass')
        self.dependent = User.objects.create_user(
            'caredependent', password='pass', email='dependent@example.com',
        )
        self.record = make_assessment(self.dependent)
        UserProfile.objects.create(user=self.owner, email_verified=True)

    def test_invite_accept_and_view_report(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('wellness:caregivers'), {
            'dependent_email': 'dependent@example.com', 'relationship': 'parent',
        })
        self.assertRedirects(response, reverse('wellness:caregivers'))
        self.assertEqual(len(mail.outbox), 1)
        link = CaregiverLink.objects.get(owner=self.owner)

        self.client.force_login(self.dependent)
        response = self.client.get(reverse('wellness:caregiver_accept', args=[link.token]))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse('wellness:caregiver_accept', args=[link.token]))
        self.assertRedirects(response, reverse('wellness:caregivers'))
        link.refresh_from_db()
        self.assertEqual(link.status, 'accepted')
        self.assertEqual(link.dependent, self.dependent)

        self.client.force_login(self.owner)
        response = self.client.get(reverse('wellness:caregiver_dashboard'))
        self.assertContains(response, 'caredependent')
        response = self.client.get(
            reverse('wellness:caregiver_report', args=[link.pk, self.record.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your Health Risk Report')

        self.client.post(reverse('wellness:caregiver_revoke', args=[link.pk]))
        link.refresh_from_db()
        self.assertEqual(link.status, 'revoked')

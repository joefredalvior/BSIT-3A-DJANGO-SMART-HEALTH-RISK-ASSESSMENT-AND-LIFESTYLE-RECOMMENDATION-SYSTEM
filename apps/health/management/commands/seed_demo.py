"""Create demo accounts and a short assessment history for local testing."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.health import engine
from apps.health.models import Assessment
from apps.health.views import _serialize_findings
from apps.users.models import UserProfile

DEMO_PASSWORD = 'demo12345'

# Each entry moves gradually from a higher-risk profile to a healthier one.
PROFILES = [
    {
        'days_ago': 180,
        'data': dict(
            age=45, sex='male', height_cm=175, weight_kg=98, waist_cm=108,
            systolic=148, diastolic=96, activity_level='sedentary',
            smoking_status='current', alcohol_status='heavy',
            diet_quality='poor', sleep_hours=5, family_history='both',
            conditions='hypertension', stress_level='high',
            fruit_veg_servings=1,
        ),
    },
    {
        'days_ago': 120,
        'data': dict(
            age=45, sex='male', height_cm=175, weight_kg=94, waist_cm=104,
            systolic=142, diastolic=92, activity_level='light',
            smoking_status='current', alcohol_status='moderate',
            diet_quality='mixed', sleep_hours=6, family_history='both',
            conditions='hypertension', stress_level='high',
            fruit_veg_servings=2,
        ),
    },
    {
        'days_ago': 60,
        'data': dict(
            age=45, sex='male', height_cm=175, weight_kg=88, waist_cm=98,
            systolic=132, diastolic=86, activity_level='moderate',
            smoking_status='former', alcohol_status='light',
            diet_quality='mixed', sleep_hours=7, family_history='both',
            conditions='prediabetes', stress_level='moderate',
            fruit_veg_servings=3,
        ),
    },
    {
        'days_ago': 7,
        'data': dict(
            age=45, sex='male', height_cm=175, weight_kg=82, waist_cm=92,
            systolic=124, diastolic=80, activity_level='active',
            smoking_status='never', alcohol_status='light',
            diet_quality='good', sleep_hours=8, family_history='cvd',
            conditions='none', stress_level='low',
            fruit_veg_servings=5,
        ),
    },
]


class Command(BaseCommand):
    help = 'Seed a demo patient, a clinician, and a short assessment history.'

    def handle(self, *args, **options):
        patient, created = User.objects.get_or_create(
            username='demo',
            defaults={
                'first_name': 'Demo',
                'last_name': 'Patient',
                'email': 'demo@example.com',
            },
        )
        if created:
            patient.set_password(DEMO_PASSWORD)
            patient.save()
            self.stdout.write(self.style.SUCCESS('Created patient: demo / demo12345'))

        clinician, created = User.objects.get_or_create(
            username='clinician',
            defaults={
                'first_name': 'Demo',
                'last_name': 'Clinician',
                'email': 'clinician@example.com',
                'is_staff': True,
            },
        )
        if created:
            clinician.set_password(DEMO_PASSWORD)
            clinician.save()
            self.stdout.write(self.style.SUCCESS(
                'Created clinician: clinician / demo12345'
            ))

        UserProfile.objects.update_or_create(
            user=patient,
            defaults={
                'birthdate': timezone.localdate() - timedelta(days=45 * 365),
                'sex': 'male',
                'height_cm': 175,
                'activity_level': 'moderate',
                'family_history': 'both',
                'conditions': 'none',
            },
        )

        Assessment.objects.filter(user=patient).delete()

        for profile in PROFILES:
            data = profile['data']
            result = engine.assess(**data)
            record = Assessment.objects.create(
                user=patient,
                **data,
                blood_pressure_band=engine.blood_pressure_band(
                    data['systolic'], data['diastolic'],
                ),
                engine_version=engine.ENGINE_VERSION,
                risk_score=result.score,
                risk_level=result.level,
                bmi=result.bmi,
                bmi_category=result.bmi_category,
                whtr=result.whtr,
                whtr_category=result.whtr_category,
                age_factor=result.age_factor,
                findings=_serialize_findings(result),
                recommendations=result.recommendations,
                targets=result.targets,
            )
            Assessment.objects.filter(pk=record.pk).update(
                created_at=timezone.now() - timedelta(days=profile['days_ago']),
            )

        self.stdout.write(self.style.SUCCESS(
            f'Seeded {len(PROFILES)} assessments for demo. '
            'Log in as demo / demo12345 or clinician / demo12345.'
        ))

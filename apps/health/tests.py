from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.health import engine
from apps.health.models import Assessment


class BMICalculationTests(TestCase):
    def test_bmi_uses_height_in_metres(self):
        self.assertEqual(engine.calculate_bmi(70, 175), 22.9)

    def test_bmi_rejects_impossible_values(self):
        self.assertIsNone(engine.calculate_bmi(0, 175))
        self.assertIsNone(engine.calculate_bmi(70, 0))
        self.assertIsNone(engine.calculate_bmi('abc', 175))

    def test_bmi_categories_follow_who_bands(self):
        self.assertEqual(engine.bmi_category(17.0), 'Underweight')
        self.assertEqual(engine.bmi_category(22.0), 'Healthy weight')
        self.assertEqual(engine.bmi_category(27.0), 'Overweight')
        self.assertEqual(engine.bmi_category(32.0), 'Obesity class I')
        self.assertEqual(engine.bmi_category(37.0), 'Obesity class II')
        self.assertEqual(engine.bmi_category(45.0), 'Obesity class III')

    def test_healthy_bmi_scores_nothing(self):
        points, _ = engine.bmi_points(22.0)
        self.assertEqual(points, 0)


class WaistTests(TestCase):
    def test_uses_sex_specific_thresholds(self):
        # 90cm is fine for a male (limit 94) but above the female limit of 80
        self.assertEqual(engine.waist_points(90, 'male')[0], 0)
        self.assertGreater(engine.waist_points(90, 'female')[0], 0)

    def test_whtr_thresholds(self):
        self.assertEqual(engine.whtr_category(0.45), 'Healthy')
        self.assertEqual(engine.whtr_category(0.55), 'Increased')
        self.assertEqual(engine.whtr_category(0.65), 'High')
        self.assertEqual(engine.whtr_points(0.45), 0)
        self.assertGreater(engine.whtr_points(0.55), 0)

    def test_whtr_is_bounded_by_the_waist_weight(self):
        self.assertEqual(engine.whtr_points(0.9), engine.WEIGHT_WAIST)


class BloodPressureTests(TestCase):
    def test_normal_reading_scores_nothing(self):
        self.assertEqual(engine.blood_pressure_points(115, 75)[0], 0)

    def test_crisis_reading_takes_the_full_weight(self):
        self.assertEqual(
            engine.blood_pressure_points(190, 125)[0],
            engine.WEIGHT_BLOOD_PRESSURE,
        )

    def test_higher_reading_never_scores_lower(self):
        stages = [
            engine.blood_pressure_points(118, 76)[0],
            engine.blood_pressure_points(125, 78)[0],
            engine.blood_pressure_points(135, 85)[0],
            engine.blood_pressure_points(145, 95)[0],
            engine.blood_pressure_points(190, 125)[0],
        ]
        self.assertEqual(stages, sorted(stages))


class FactorTests(TestCase):
    def test_age_factor_increases_with_age(self):
        self.assertEqual(engine.age_factor(30), 1.0)
        self.assertLess(engine.age_factor(30), engine.age_factor(50))
        self.assertLess(engine.age_factor(50), engine.age_factor(70))

    def test_diet_penalises_low_fruit_and_vegetables(self):
        self.assertLess(
            engine.diet_points('good', 5),
            engine.diet_points('good', 1),
        )

    def test_new_factors_are_bounded(self):
        self.assertEqual(engine.stress_points('high'), engine.WEIGHT_STRESS)
        self.assertEqual(
            engine.family_history_points('both'), engine.WEIGHT_FAMILY_HISTORY,
        )
        self.assertEqual(
            engine.conditions_points('diabetes'), engine.WEIGHT_CONDITIONS,
        )

    def test_healthy_weight_range(self):
        low, high = engine.healthy_weight_range(175)
        self.assertAlmostEqual(low, 56.7, places=1)
        self.assertAlmostEqual(high, 76.3, places=1)


class AssessmentTests(TestCase):
    healthy = dict(
        age=30, sex='female', height_cm=168, weight_kg=60, waist_cm=70,
        systolic=115, diastolic=75,
        activity_level='active', smoking_status='never',
        alcohol_status='none', diet_quality='good', sleep_hours=8,
    )

    def test_healthy_lifestyle_scores_low_risk(self):
        result = engine.assess(**self.healthy)
        self.assertEqual(result.level, engine.RISK_LOW)
        self.assertEqual(result.score, 0)
        self.assertEqual(result.findings, [])
        self.assertEqual(result.recommendations, [])
        self.assertFalse(result.top_recommendations)

    def test_unhealthy_lifestyle_scores_critical(self):
        result = engine.assess(**dict(
            self.healthy, weight_kg=120, waist_cm=110, systolic=190, diastolic=125,
            activity_level='sedentary', smoking_status='current',
            alcohol_status='heavy', diet_quality='poor', sleep_hours=4,
            stress_level='high', family_history='both', conditions='diabetes',
        ))
        self.assertEqual(result.level, engine.RISK_CRITICAL)
        # Every weighted factor maxed, so this should land in the top band.
        self.assertGreaterEqual(result.score, 90)

    def test_severe_obesity_maxes_the_bmi_weight(self):
        # BMI of roughly 45 is deep in the top category and must not be
        # scored as if it were merely overweight.
        points, _ = engine.bmi_points(45.0)
        self.assertEqual(points, engine.WEIGHT_BMI)

    def test_score_stays_within_bounds_for_any_input(self):
        result = engine.assess(**dict(
            self.healthy, weight_kg=300, systolic=250, diastolic=150,
            activity_level='sedentary', smoking_status='current',
            alcohol_status='heavy', diet_quality='poor', sleep_hours=0,
            stress_level='high', family_history='both', conditions='kidney',
        ))
        self.assertGreaterEqual(result.score, 0)
        self.assertLessEqual(result.score, 100)

    def test_every_finding_carries_actionable_advice_and_a_target(self):
        result = engine.assess(**dict(self.healthy, smoking_status='current'))
        self.assertTrue(result.findings)
        for finding in result.findings:
            self.assertTrue(finding.advice.strip())
            self.assertTrue(finding.target.strip())
            self.assertTrue(0 < finding.points <= finding.max_points)

    def test_findings_are_ordered_by_contribution(self):
        result = engine.assess(**dict(
            self.healthy, weight_kg=120, waist_cm=110, systolic=190,
            diastolic=125, smoking_status='current', diet_quality='poor',
        ))
        points = [finding.points for finding in result.findings]
        self.assertEqual(points, sorted(points, reverse=True))

    def test_recommendations_cover_every_finding_and_are_prioritised(self):
        result = engine.assess(**dict(
            self.healthy, smoking_status='current', diet_quality='poor',
            conditions='diabetes',
        ))
        self.assertEqual(len(result.recommendations), len(result.findings))
        self.assertEqual(
            [rec['points_saved'] for rec in result.recommendations],
            sorted((rec['points_saved'] for rec in result.recommendations), reverse=True),
        )
        self.assertEqual(
            [rec['priority'] for rec in result.recommendations],
            list(range(1, len(result.recommendations) + 1)),
        )
        self.assertLessEqual(len(result.top_recommendations), 3)

    def test_recommendations_are_structured(self):
        result = engine.assess(**dict(self.healthy, smoking_status='current'))
        rec = result.recommendations[0]
        for key in ('key', 'title', 'category', 'points_saved', 'priority',
                    'advice', 'target', 'timeframe', 'action_steps'):
            self.assertIn(key, rec)
        self.assertTrue(rec['action_steps'])

    def test_targets_are_personalised(self):
        result = engine.assess(**self.healthy)
        labels = [target['label'] for target in result.targets]
        self.assertIn('Weight', labels)
        weight_target = next(t for t in result.targets if t['label'] == 'Weight')
        self.assertIn('kg', weight_target['target'])
        self.assertEqual(weight_target['status'], 'good')


class AssessmentViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('formuser', password='pass')
        self.client.force_login(self.user)
        self.data = {
            'age': '40', 'sex': 'male', 'height_cm': '175', 'weight_kg': '80',
            'waist_cm': '90', 'systolic': '120', 'diastolic': '80',
            'activity_level': 'moderate', 'smoking_status': 'never',
            'alcohol_status': 'light', 'diet_quality': 'mixed',
            'sleep_hours': '7', 'family_history': 'none',
            'conditions': 'none', 'stress_level': 'low',
            'fruit_veg_servings': '5',
        }

    def test_assessment_form_renders(self):
        response = self.client.get(reverse('health:assessment_form'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Family history')

    def test_post_creates_record_with_real_json_lists(self):
        response = self.client.post(reverse('health:assessment_form'), self.data)
        self.assertEqual(response.status_code, 302)

        record = Assessment.objects.get(user=self.user)
        self.assertIsInstance(record.findings, list)
        self.assertIsInstance(record.recommendations, list)
        self.assertIsInstance(record.targets, list)
        self.assertEqual(record.engine_version, engine.ENGINE_VERSION)
        self.assertIn(record.risk_level, dict(Assessment.LEVEL_CHOICES))

        report = self.client.get(reverse('health:report', args=[record.pk]))
        self.assertEqual(report.status_code, 200)
        self.assertContains(report, 'Health Risk Report')

    def test_invalid_post_redisplays_form(self):
        bad = dict(self.data, weight_kg='5')
        response = self.client.post(reverse('health:assessment_form'), bad)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter a value between')
        self.assertEqual(Assessment.objects.count(), 0)

    def test_export_returns_excel_workbook(self):
        self.client.post(reverse('health:assessment_form'), self.data)
        record = Assessment.objects.get(user=self.user)
        response = self.client.get(reverse('health:export', args=[record.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('attachment', response['Content-Disposition'])

    def test_history_renders_with_multiple_records(self):
        self.client.post(reverse('health:assessment_form'), self.data)
        self.client.post(reverse('health:assessment_form'), dict(
            self.data, risk_score='55',
        ))
        response = self.client.get(reverse('health:history'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Assessment History')


class HistoryViewTests(TestCase):
    """Regression: the history page used to 500 once a user had 2+ records.

    The trend payload passed a raw datetime into json.dumps, which raises
    TypeError. The trend was unused by the template, so it was removed. The
    trend is now built as plain strings and covered by the view tests above.
    """

    def setUp(self):
        self.user = User.objects.create_user('histuser', password='pass')
        self.client.force_login(self.user)

    def _make_assessment(self, **overrides):
        fields = dict(
            user=self.user, age=40, sex='male', height_cm=175, weight_kg=80,
            waist_cm=90, systolic=120, diastolic=80, blood_pressure_band='normal',
            activity_level='moderate', smoking_status='never',
            alcohol_status='light', diet_quality='mixed', sleep_hours=7,
            risk_score=30, risk_level='Moderate', bmi=26.1,
            bmi_category='Overweight', findings=[], recommendations=[],
            targets=[],
        )
        fields.update(overrides)
        return Assessment.objects.create(**fields)

    def test_history_renders_with_no_records(self):
        response = self.client.get('/health/history/')
        self.assertEqual(response.status_code, 200)

    def test_history_renders_with_multiple_records(self):
        self._make_assessment()
        self._make_assessment(risk_score=55, risk_level='High')
        response = self.client.get('/health/history/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '55')


class ProfilePrefillTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('prefill', password='pass')
        self.client.force_login(self.user)
        from apps.users.models import UserProfile
        UserProfile.objects.create(
            user=self.user, sex='female', height_cm=165,
            activity_level='light', family_history='cvd',
        )

    def test_form_prefills_from_profile(self):
        response = self.client.get(reverse('health:assessment_form'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="165"')
        self.assertContains(response, 'value="cvd" selected')


class ClinicianTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            'clinician', password='pass', is_staff=True,
        )
        self.patient = User.objects.create_user('patient', password='pass')
        Assessment.objects.create(
            user=self.patient, age=50, sex='male', height_cm=180,
            weight_kg=95, waist_cm=100, systolic=145, diastolic=95,
            blood_pressure_band='stage2', activity_level='light',
            smoking_status='former', alcohol_status='moderate',
            diet_quality='mixed', sleep_hours=6, risk_score=52,
            risk_level='High', bmi=29.3, bmi_category='Overweight',
            findings=[], recommendations=[], targets=[],
        )

    def test_staff_can_see_patient_assessments(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('users:clinician'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'patient')

    def test_staff_can_open_any_report(self):
        record = Assessment.objects.first()
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse('health:clinician_report', args=[record.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Patient')

    def test_patient_cannot_open_clinician_dashboard(self):
        self.client.force_login(self.patient)
        response = self.client.get(reverse('users:clinician'))
        self.assertEqual(response.status_code, 302)


class ProfileFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('profileuser', password='pass')
        self.client.force_login(self.user)

    def test_profile_page_renders(self):
        response = self.client.get(reverse('users:profile'))
        self.assertEqual(response.status_code, 200)

    def test_profile_can_be_saved(self):
        response = self.client.post(reverse('users:profile'), {
            'birthdate': '1990-05-10',
            'sex': 'male',
            'height_cm': '180',
            'activity_level': 'active',
            'family_history': 'diabetes',
            'conditions': 'none',
        })
        self.assertEqual(response.status_code, 302)

        from apps.users.models import UserProfile
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.height_cm, 180)
        self.assertEqual(profile.family_history, 'diabetes')


class GuideTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('guideuser', password='pass')
        self.client.force_login(self.user)

    def test_guide_renders(self):
        response = self.client.get(reverse('info:guide'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Body mass index')


class AssessmentDeleteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('deleter', password='pass')
        self.other = User.objects.create_user('other', password='pass')
        self.client.force_login(self.user)
        self.record = Assessment.objects.create(
            user=self.user, age=35, sex='female', height_cm=165, weight_kg=65,
            waist_cm=75, systolic=118, diastolic=76, blood_pressure_band='normal',
            activity_level='moderate', smoking_status='never',
            alcohol_status='none', diet_quality='good', sleep_hours=8,
            risk_score=6, risk_level='Low', bmi=23.9, bmi_category='Healthy weight',
            findings=[], recommendations=[], targets=[],
        )

    def test_delete_removes_record(self):
        response = self.client.post(reverse('health:delete', args=[self.record.pk]))
        self.assertRedirects(response, reverse('health:history'))
        self.assertFalse(Assessment.objects.filter(pk=self.record.pk).exists())

    def test_get_is_not_allowed(self):
        response = self.client.get(reverse('health:delete', args=[self.record.pk]))
        self.assertEqual(response.status_code, 405)

    def test_cannot_delete_another_users_record(self):
        foreign = Assessment.objects.create(
            user=self.other, age=50, sex='male', height_cm=175, weight_kg=80,
            waist_cm=90, systolic=120, diastolic=80, blood_pressure_band='normal',
            activity_level='light', smoking_status='never',
            alcohol_status='light', diet_quality='mixed', sleep_hours=7,
            risk_score=20, risk_level='Low', bmi=26.1, bmi_category='Overweight',
            findings=[], recommendations=[], targets=[],
        )
        response = self.client.post(reverse('health:delete', args=[foreign.pk]))
        self.assertEqual(response.status_code, 404)


class HistoryPaginationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('pager', password='pass')
        self.client.force_login(self.user)
        for index in range(12):
            Assessment.objects.create(
                user=self.user, age=40, sex='male', height_cm=175, weight_kg=80,
                waist_cm=90, systolic=120, diastolic=80,
                blood_pressure_band='normal', activity_level='light',
                smoking_status='never', alcohol_status='light',
                diet_quality='mixed', sleep_hours=7, risk_score=index,
                risk_level='Low', bmi=26.1, bmi_category='Overweight',
                findings=[], recommendations=[], targets=[],
            )

    def test_second_page_only_shows_remaining_records(self):
        response = self.client.get(reverse('health:history'), {'page': 2})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Showing 11 to 12 of 12')


class ProjectedScoreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('projector', password='pass')
        self.client.force_login(self.user)
        self.record = Assessment.objects.create(
            user=self.user, age=50, sex='male', height_cm=175, weight_kg=95,
            waist_cm=100, systolic=145, diastolic=95,
            blood_pressure_band='stage2', activity_level='sedentary',
            smoking_status='current', alcohol_status='heavy',
            diet_quality='poor', sleep_hours=5, risk_score=70,
            risk_level='High', bmi=31.0, bmi_category='Obesity class I',
            findings=[], recommendations=[
                {'points_saved': 10, 'modifiable': True, 'title': 'A'},
                {'points_saved': 5, 'modifiable': True, 'title': 'B'},
                {'points_saved': 5, 'modifiable': False, 'title': 'C'},
            ], targets=[],
        )

    def test_projected_score_only_counts_modifiable_findings(self):
        response = self.client.get(reverse('health:report', args=[self.record.pk]))
        self.assertEqual(response.status_code, 200)
        # 15 modifiable points out of 100 is 15% of MAX_SCORE -> 70 - 15 = 55.
        self.assertEqual(response.context['projected_score'], 55)


class MVPJourneyTests(TestCase):
    """The end-to-end path that defines the minimum viable product."""

    assessment = {
        'age': '35', 'sex': 'female', 'height_cm': '165', 'weight_kg': '62',
        'waist_cm': '74', 'systolic': '118', 'diastolic': '76',
        'activity_level': 'moderate', 'smoking_status': 'never',
        'alcohol_status': 'light', 'diet_quality': 'good',
        'sleep_hours': '8', 'family_history': 'none',
        'conditions': 'none', 'stress_level': 'low',
        'fruit_veg_servings': '5',
    }

    def test_register_assess_report_history_flow(self):
        response = self.client.post(reverse('register'), {
            'username': 'mvpuser',
            'first_name': 'Mvp',
            'last_name': 'User',
            'email': 'mvp@example.com',
            'password': 'Xk9!mQ2#Lp',
            'confirm_password': 'Xk9!mQ2#Lp',
        })
        self.assertRedirects(response, reverse('dashboard'))

        response = self.client.post(
            reverse('health:assessment_form'), self.assessment,
        )
        self.assertEqual(response.status_code, 302)

        record = Assessment.objects.get(user__username='mvpuser')
        report = self.client.get(reverse('health:report', args=[record.pk]))
        self.assertEqual(report.status_code, 200)
        self.assertContains(report, 'Your Health Risk Report')
        self.assertContains(report, 'Your personalised targets')

        history = self.client.get(reverse('health:history'))
        self.assertEqual(history.status_code, 200)
        self.assertContains(history, 'Assessment History')
        self.assertContains(history, str(record.risk_score))


class DataIsolationTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', password='pass')
        self.bob = User.objects.create_user('bob', password='pass')
        self.record = Assessment.objects.create(
            user=self.alice, age=40, sex='female', height_cm=165, weight_kg=65,
            waist_cm=75, systolic=118, diastolic=76, blood_pressure_band='normal',
            activity_level='moderate', smoking_status='never',
            alcohol_status='none', diet_quality='good', sleep_hours=8,
            risk_score=5, risk_level='Low', bmi=23.9,
            bmi_category='Healthy weight', findings=[], recommendations=[],
            targets=[],
        )

    def test_other_user_cannot_view_report(self):
        self.client.force_login(self.bob)
        response = self.client.get(reverse('health:report', args=[self.record.pk]))
        self.assertEqual(response.status_code, 404)

    def test_other_user_history_does_not_include_record(self):
        self.client.force_login(self.bob)
        response = self.client.get(reverse('health:history'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No assessments yet')
        self.assertNotContains(response, 'View report')

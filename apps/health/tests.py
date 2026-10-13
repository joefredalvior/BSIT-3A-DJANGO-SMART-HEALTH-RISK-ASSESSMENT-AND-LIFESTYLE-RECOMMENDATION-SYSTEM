from django.test import TestCase

from apps.health import engine


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

    def test_unhealthy_lifestyle_scores_critical(self):
        result = engine.assess(**dict(
            self.healthy, weight_kg=120, waist_cm=110, systolic=190, diastolic=125,
            activity_level='sedentary', smoking_status='current',
            alcohol_status='heavy', diet_quality='poor', sleep_hours=4,
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
        ))
        self.assertGreaterEqual(result.score, 0)
        self.assertLessEqual(result.score, 100)

    def test_every_finding_carries_actionable_advice(self):
        result = engine.assess(**dict(self.healthy, smoking_status='current'))
        self.assertTrue(result.findings)
        for finding in result.findings:
            self.assertTrue(finding.advice.strip())

    def test_recommendations_cover_every_finding(self):
        result = engine.assess(**dict(
            self.healthy, smoking_status='current', diet_quality='poor',
        ))
        self.assertEqual(len(result.recommendations), len(result.findings))


class HistoryViewTests(TestCase):
    """Regression: the history page used to 500 once a user had 2+ records.

    The trend payload passed a raw datetime into json.dumps, which raises
    TypeError. The trend was unused by the template, so it was removed.
    """

    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user('histuser', password='pass')
        self.client.force_login(self.user)

    def _make_assessment(self, **overrides):
        from apps.health.models import Assessment
        fields = dict(
            user=self.user, age=40, sex='male', height_cm=175, weight_kg=80,
            waist_cm=90, systolic=120, diastolic=80, blood_pressure_band='normal',
            activity_level='moderate', smoking_status='never',
            alcohol_status='light', diet_quality='mixed', sleep_hours=7,
            risk_score=30, risk_level='Moderate', bmi=26.1,
            bmi_category='Overweight', findings='[]', recommendations='[]',
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
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from . import engine


class Assessment(models.Model):
    """One completed health risk assessment and its advisory output."""

    LOW = engine.RISK_LOW
    MODERATE = engine.RISK_MODERATE
    HIGH = engine.RISK_HIGH
    CRITICAL = engine.RISK_CRITICAL

    LEVEL_CHOICES = [
        (LOW, 'Low risk'),
        (MODERATE, 'Moderate risk'),
        (HIGH, 'High risk'),
        (CRITICAL, 'Critical risk'),
    ]

    ACTIVITY_CHOICES = engine.ACTIVITY_LEVELS
    SMOKING_CHOICES = engine.SMOKING_STATUS
    ALCOHOL_CHOICES = engine.ALCOHOL_STATUS
    DIET_CHOICES = engine.DIET_QUALITY
    SEX_CHOICES = engine.SEX_CHOICES
    BP_BAND_CHOICES = engine.BLOOD_PRESSURE_BANDS
    FAMILY_HISTORY_CHOICES = engine.FAMILY_HISTORY_CHOICES
    CONDITION_CHOICES = engine.CONDITION_CHOICES
    STRESS_CHOICES = engine.STRESS_CHOICES

    # --- inputs ---
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='assessments',
        on_delete=models.CASCADE,
    )
    age = models.PositiveSmallIntegerField(validators=[MinValueValidator(13), MaxValueValidator(100)])
    sex = models.CharField(max_length=10, choices=SEX_CHOICES)
    height_cm = models.PositiveSmallIntegerField(validators=[MinValueValidator(100), MaxValueValidator(250)])
    weight_kg = models.DecimalField(max_digits=5, decimal_places=1, validators=[MinValueValidator(30), MaxValueValidator(300)])
    waist_cm = models.PositiveSmallIntegerField(validators=[MinValueValidator(40), MaxValueValidator(200)])
    systolic = models.PositiveSmallIntegerField(validators=[MinValueValidator(70), MaxValueValidator(250)])
    diastolic = models.PositiveSmallIntegerField(validators=[MinValueValidator(40), MaxValueValidator(150)])
    blood_pressure_band = models.CharField(max_length=10, choices=BP_BAND_CHOICES, default='normal')
    activity_level = models.CharField(max_length=15, choices=ACTIVITY_CHOICES)
    smoking_status = models.CharField(max_length=15, choices=SMOKING_CHOICES)
    alcohol_status = models.CharField(max_length=15, choices=ALCOHOL_CHOICES)
    diet_quality = models.CharField(max_length=10, choices=DIET_CHOICES)
    sleep_hours = models.DecimalField(max_digits=3, decimal_places=1, validators=[MinValueValidator(0), MaxValueValidator(16)])
    family_history = models.CharField(max_length=10, choices=FAMILY_HISTORY_CHOICES, default='none')
    conditions = models.CharField(max_length=15, choices=CONDITION_CHOICES, default='none')
    stress_level = models.CharField(max_length=10, choices=STRESS_CHOICES, default='low')
    fruit_veg_servings = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(0), MaxValueValidator(15)],
    )

    # --- outputs ---
    engine_version = models.CharField(max_length=10, default=engine.ENGINE_VERSION)
    risk_score = models.PositiveSmallIntegerField(default=0)
    risk_level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default=LOW)
    bmi = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    bmi_category = models.CharField(max_length=30, blank=True)
    whtr = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    whtr_category = models.CharField(max_length=30, blank=True)
    age_factor = models.DecimalField(max_digits=4, decimal_places=2, default=1.0)
    findings = models.JSONField(default=list)
    recommendations = models.JSONField(default=list)
    targets = models.JSONField(default=list)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'health assessment'
        verbose_name_plural = 'health assessments'

    def __str__(self):
        return f'{self.user.username} - {self.risk_level} ({self.risk_score}) on {self.created_at:%Y-%m-%d}'

    def _as_list(self, value):
        return value if isinstance(value, list) else []

    @property
    def level_colour(self):
        return engine.LEVEL_COLOURS.get(self.risk_level, 'secondary')

    @property
    def summary(self):
        return engine.LEVEL_SUMMARY.get(self.risk_level, '')

    @property
    def finding_list(self):
        return self._as_list(self.findings)

    @property
    def recommendation_list(self):
        return self._as_list(self.recommendations)

    @property
    def top_recommendations(self):
        return self.recommendation_list[:3]

    @property
    def target_list(self):
        return self._as_list(self.targets)

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

    # --- outputs ---
    risk_score = models.PositiveSmallIntegerField(default=0)
    risk_level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default=LOW)
    bmi = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    bmi_category = models.CharField(max_length=30, blank=True)
    findings = models.JSONField(default=list)
    recommendations = models.JSONField(default=list)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'health assessment'
        verbose_name_plural = 'health assessments'

    def __str__(self):
        return f'{self.user.username} - {self.risk_level} ({self.risk_score}) on {self.created_at:%Y-%m-%d}'

    @property
    def level_colour(self):
        return engine.LEVEL_COLOURS.get(self.risk_level, 'secondary')

    @property
    def summary(self):
        return engine.LEVEL_SUMMARY.get(self.risk_level, '')
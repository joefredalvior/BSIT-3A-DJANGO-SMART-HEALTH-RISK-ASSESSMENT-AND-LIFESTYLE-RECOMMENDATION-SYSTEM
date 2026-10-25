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
        indexes = [
            models.Index(fields=['user', '-created_at'], name='assessment_user_recent_idx'),
            models.Index(fields=['risk_level', '-created_at'], name='assessment_risk_recent_idx'),
        ]

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


class ClinicianNote(models.Model):
    """A clinician's follow-up note attached to one assessment."""

    assessment = models.ForeignKey(
        Assessment,
        related_name='clinician_notes',
        on_delete=models.CASCADE,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='clinical_notes',
        on_delete=models.SET_NULL,
        null=True,
    )
    note = models.TextField()
    follow_up_required = models.BooleanField(default=False)
    follow_up_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'clinician note'
        verbose_name_plural = 'clinician notes'

    def __str__(self):
        return f'Note on assessment {self.assessment_id} by {self.author or "removed user"}'


class HealthGoal(models.Model):
    """A user-defined target tracked against future assessments."""

    METRIC_CHOICES = [
        ('risk_score', 'Risk score'),
        ('bmi', 'Body mass index'),
        ('weight_kg', 'Weight (kg)'),
        ('waist_cm', 'Waist (cm)'),
        ('systolic', 'Systolic blood pressure'),
        ('diastolic', 'Diastolic blood pressure'),
        ('sleep_hours', 'Sleep (hours)'),
        ('fruit_veg_servings', 'Fruit & vegetable servings'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='health_goals',
        on_delete=models.CASCADE,
    )
    metric = models.CharField(max_length=24, choices=METRIC_CHOICES)
    label = models.CharField(max_length=80, blank=True)
    target_value = models.DecimalField(max_digits=6, decimal_places=1)
    unit = models.CharField(max_length=20, blank=True)
    due_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['is_active', 'due_date', '-created_at']
        verbose_name = 'health goal'
        verbose_name_plural = 'health goals'
        indexes = [
            models.Index(fields=['user', 'is_active'], name='goal_user_active_idx'),
        ]

    def __str__(self):
        return f'{self.user.username}: {self.metric} -> {self.target_value}'

    @property
    def display_label(self):
        return self.label or self.get_metric_display()



def _share_token():
    import secrets
    return secrets.token_urlsafe(32)


class ReportShare(models.Model):
    """A revocable, expiring read-only link to one assessment report."""

    assessment = models.ForeignKey(
        Assessment,
        related_name='shares',
        on_delete=models.CASCADE,
    )
    token = models.CharField(max_length=64, unique=True, default=_share_token)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_report_shares',
        on_delete=models.SET_NULL,
        null=True,
    )
    expires_at = models.DateTimeField()
    view_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'report share'
        verbose_name_plural = 'report shares'

    @property
    def is_expired(self):
        from django.utils import timezone
        return timezone.now() >= self.expires_at

    @property
    def is_valid(self):
        return self.is_active and not self.is_expired

    def __str__(self):
        return f'Share for assessment {self.assessment_id}'


class Achievement(models.Model):
    """A small, automatically awarded milestone."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='achievements',
        on_delete=models.CASCADE,
    )
    code = models.CharField(max_length=40)
    title = models.CharField(max_length=80)
    description = models.CharField(max_length=200)
    icon = models.CharField(max_length=40, default='fa-award')
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-awarded_at']
        verbose_name = 'achievement'
        verbose_name_plural = 'achievements'
        constraints = [
            models.UniqueConstraint(fields=['user', 'code'], name='unique_user_achievement'),
        ]

    def __str__(self):
        return f'{self.user.username}: {self.title}'

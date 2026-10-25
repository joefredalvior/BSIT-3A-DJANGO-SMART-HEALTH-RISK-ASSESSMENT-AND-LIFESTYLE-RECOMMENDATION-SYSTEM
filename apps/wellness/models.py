from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


def _invite_token():
    import secrets
    return secrets.token_urlsafe(24)


class VitalReading(models.Model):
    """A day-to-day measurement, separate from a full assessment."""

    SOURCE_CHOICES = [
        ('manual', 'Entered manually'),
        ('import', 'Imported from device/export'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='vital_readings',
        on_delete=models.CASCADE,
    )
    measured_at = models.DateTimeField(default=timezone.now, db_index=True)
    weight_kg = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(20), MaxValueValidator(400)],
    )
    waist_cm = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(30), MaxValueValidator(250)],
    )
    systolic = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(60), MaxValueValidator(260)],
    )
    diastolic = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(30), MaxValueValidator(160)],
    )
    sleep_hours = models.DecimalField(
        max_digits=3, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(24)],
    )
    exercise_minutes = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1440)],
    )
    note = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='manual')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-measured_at']
        verbose_name = 'vital reading'
        verbose_name_plural = 'vital readings'
        indexes = [
            models.Index(fields=['user', '-measured_at'], name='vital_user_recent_idx'),
        ]

    def __str__(self):
        return f'{self.user.username} on {self.measured_at:%Y-%m-%d}'

    @property
    def bmi(self):
        if not self.weight_kg:
            return None
        latest = self.user.assessments.first()
        if latest is None or not latest.height_cm:
            return None
        height_m = latest.height_cm / 100
        return round(float(self.weight_kg) / (height_m * height_m), 1)

    @property
    def blood_pressure_display(self):
        if self.systolic and self.diastolic:
            return f'{self.systolic}/{self.diastolic}'
        return '-'


class Appointment(models.Model):
    """A patient request for a clinic appointment."""

    STATUS_CHOICES = [
        ('requested', 'Requested'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='appointments',
        on_delete=models.CASCADE,
    )
    clinician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='clinician_appointments',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    scheduled_for = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=30)
    reason = models.CharField(max_length=200)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='requested')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['scheduled_for']
        verbose_name = 'appointment'
        verbose_name_plural = 'appointments'
        indexes = [
            models.Index(fields=['patient', 'scheduled_for'], name='appt_patient_date_idx'),
            models.Index(fields=['clinician', 'scheduled_for'], name='appt_clinician_date_idx'),
        ]

    def __str__(self):
        return f'{self.patient.username} with {self.clinician or "unassigned"} on {self.scheduled_for:%Y-%m-%d %H:%M}'


class SecureMessage(models.Model):
    """A private message between a patient and a clinician."""

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='sent_secure_messages',
        on_delete=models.CASCADE,
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='received_secure_messages',
        on_delete=models.CASCADE,
    )
    assessment = models.ForeignKey(
        'health.Assessment',
        related_name='secure_messages',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    subject = models.CharField(max_length=120, blank=True)
    body = models.TextField()
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'secure message'
        verbose_name_plural = 'secure messages'
        indexes = [
            models.Index(fields=['recipient', '-created_at'], name='msg_recipient_recent_idx'),
        ]

    def __str__(self):
        return f'{self.sender.username} -> {self.recipient.username}: {self.subject or self.body[:40]}'


class MentalHealthScreening(models.Model):
    """A PHQ-9 or GAD-7 screening result."""

    KIND_CHOICES = [
        ('phq9', 'PHQ-9 depression screening'),
        ('gad7', 'GAD-7 anxiety screening'),
    ]
    SEVERITY_CHOICES = [
        ('minimal', 'Minimal'),
        ('mild', 'Mild'),
        ('moderate', 'Moderate'),
        ('moderately_severe', 'Moderately severe'),
        ('severe', 'Severe'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='mental_health_screenings',
        on_delete=models.CASCADE,
    )
    kind = models.CharField(max_length=6, choices=KIND_CHOICES)
    answers = models.JSONField(default=list)
    score = models.PositiveSmallIntegerField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'mental health screening'
        verbose_name_plural = 'mental health screenings'
        indexes = [
            models.Index(fields=['user', '-created_at'], name='mh_user_recent_idx'),
        ]

    def __str__(self):
        return f'{self.user.username}: {self.get_kind_display()} ({self.score})'


class Medication(models.Model):
    """A medication the patient is taking, with optional reminder time."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='medications',
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=120)
    dosage = models.CharField(max_length=80, blank=True)
    frequency = models.CharField(max_length=80, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    reminder_time = models.TimeField(null=True, blank=True)
    last_reminder_sent = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['is_active', 'name']
        verbose_name = 'medication'
        verbose_name_plural = 'medications'
        indexes = [
            models.Index(fields=['user', 'is_active'], name='med_user_active_idx'),
        ]

    def __str__(self):
        return f'{self.user.username}: {self.name}'


class Clinic(models.Model):
    """A clinic or health centre shown in the referral directory."""

    name = models.CharField(max_length=160)
    address = models.CharField(max_length=240)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    services = models.CharField(max_length=240, blank=True)
    opening_hours = models.CharField(max_length=160, blank=True)
    is_partner = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'clinic'
        verbose_name_plural = 'clinics'

    def __str__(self):
        return self.name


class ReportFeedback(models.Model):
    """A rating and optional comment on a report."""

    assessment = models.ForeignKey(
        'health.Assessment',
        related_name='feedback',
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='report_feedback',
        on_delete=models.CASCADE,
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'report feedback'
        verbose_name_plural = 'report feedback'
        constraints = [
            models.UniqueConstraint(
                fields=['assessment', 'user'], name='unique_feedback_per_user_report',
            ),
        ]

    def __str__(self):
        return f'{self.user.username} rated {self.assessment_id}: {self.rating}/5'


class CaregiverLink(models.Model):
    """An accepted link letting a caregiver view a dependent's reports."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('revoked', 'Revoked'),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='caregiver_links',
        on_delete=models.CASCADE,
    )
    dependent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='caregiver_access',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    dependent_email = models.EmailField()
    relationship = models.CharField(max_length=80, blank=True)
    token = models.CharField(max_length=64, unique=True, default=_invite_token)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'caregiver link'
        verbose_name_plural = 'caregiver links'

    def __str__(self):
        return f'{self.owner.username} -> {self.dependent_email} ({self.status})'

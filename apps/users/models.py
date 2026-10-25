from datetime import date

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.health import engine


class UserProfile(models.Model):
    """Baseline details used to prefill health assessments."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name='profile',
        on_delete=models.CASCADE,
    )
    birthdate = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=10, choices=engine.SEX_CHOICES, blank=True)
    height_cm = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(100), MaxValueValidator(250)],
    )
    activity_level = models.CharField(
        max_length=15, choices=engine.ACTIVITY_LEVELS, blank=True,
    )
    family_history = models.CharField(
        max_length=10, choices=engine.FAMILY_HISTORY_CHOICES, default='none',
    )
    conditions = models.CharField(
        max_length=15, choices=engine.CONDITION_CHOICES, default='none',
    )
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    consent_at = models.DateTimeField(null=True, blank=True)
    consent_version = models.CharField(max_length=20, blank=True)
    reminder_opt_in = models.BooleanField(default=True)
    last_reminder_sent = models.DateTimeField(null=True, blank=True)
    last_digest_sent = models.DateTimeField(null=True, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    sms_opt_in = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'user profile'
        verbose_name_plural = 'user profiles'

    def __str__(self):
        return f'Profile for {self.user.username}'

    @property
    def age(self):
        if not self.birthdate:
            return ''
        today = date.today()
        years = today.year - self.birthdate.year
        if (today.month, today.day) < (self.birthdate.month, self.birthdate.day):
            years -= 1
        return max(years, 0)


class UserTwoFactor(models.Model):
    """TOTP two-factor settings for one user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name='two_factor',
        on_delete=models.CASCADE,
    )
    secret = models.CharField(max_length=64, blank=True)
    enabled = models.BooleanField(default=False)
    backup_codes = models.JSONField(default=list, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'2FA for {self.user.username} ({"on" if self.enabled else "off"})'

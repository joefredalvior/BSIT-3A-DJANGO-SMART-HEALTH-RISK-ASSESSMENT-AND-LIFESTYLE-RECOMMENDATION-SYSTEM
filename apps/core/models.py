from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """Append-only record of security and privacy relevant actions."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='audit_events',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    action = models.CharField(max_length=64, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'audit event'
        verbose_name_plural = 'audit events'
        indexes = [
            models.Index(fields=['action', 'created_at']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        who = self.user.get_username() if self.user else 'anonymous'
        return f'{self.action} by {who} at {self.created_at:%Y-%m-%d %H:%M}'


class LoginAttempt(models.Model):
    """Persistent failed-login counter keyed by username and client IP."""

    username = models.CharField(max_length=150, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_attempt_at']
        verbose_name = 'login attempt'
        verbose_name_plural = 'login attempts'
        constraints = [
            models.UniqueConstraint(
                fields=['username', 'ip_address'],
                name='unique_login_attempt_per_username_ip',
            ),
        ]

    def __str__(self):
        return f'{self.username} ({self.ip_address or "unknown"}): {self.failed_attempts}'


class UserSession(models.Model):
    """A lightweight record of signed-in sessions for the account security page."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='tracked_sessions',
        on_delete=models.CASCADE,
    )
    session_key = models.CharField(max_length=64, unique=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-last_seen']
        verbose_name = 'user session'
        verbose_name_plural = 'user sessions'

    @property
    def is_active(self):
        return self.ended_at is None

    def __str__(self):
        return f'{self.user.username} session ending {self.last_seen:%Y-%m-%d %H:%M}'

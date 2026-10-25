from django.contrib import admin

from .models import AuditEvent, LoginAttempt, UserSession


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ('action', 'user', 'ip_address', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('user__username', 'action', 'ip_address')
    readonly_fields = (
        'user', 'action', 'ip_address', 'user_agent', 'metadata', 'created_at',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ('username', 'ip_address', 'failed_attempts', 'locked_until', 'last_attempt_at')
    list_filter = ('locked_until',)
    search_fields = ('username', 'ip_address')


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'ip_address', 'created_at', 'last_seen', 'ended_at')
    list_filter = ('created_at', 'last_seen')
    search_fields = ('user__username', 'ip_address', 'session_key')
    readonly_fields = ('user', 'session_key', 'ip_address', 'user_agent', 'created_at', 'last_seen')

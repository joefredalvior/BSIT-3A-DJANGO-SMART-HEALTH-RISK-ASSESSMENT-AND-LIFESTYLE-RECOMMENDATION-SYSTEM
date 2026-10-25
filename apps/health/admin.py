from django.contrib import admin

from .models import Assessment, Achievement, ClinicianNote, HealthGoal, ReportShare


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'risk_level', 'risk_score', 'bmi', 'whtr',
        'engine_version', 'created_at',
    )
    list_filter = ('risk_level', 'engine_version', 'created_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = (
        'engine_version', 'risk_score', 'risk_level', 'bmi', 'bmi_category',
        'whtr', 'whtr_category', 'age_factor', 'findings', 'recommendations',
        'targets', 'created_at',
    )


@admin.register(ClinicianNote)
class ClinicianNoteAdmin(admin.ModelAdmin):
    list_display = ('assessment', 'author', 'follow_up_required', 'follow_up_date', 'created_at')
    list_filter = ('follow_up_required', 'follow_up_date')
    search_fields = ('assessment__user__username', 'note', 'author__username')


@admin.register(HealthGoal)
class HealthGoalAdmin(admin.ModelAdmin):
    list_display = ('user', 'metric', 'target_value', 'unit', 'is_active', 'due_date')
    list_filter = ('metric', 'is_active')
    search_fields = ('user__username', 'label')


@admin.register(ReportShare)
class ReportShareAdmin(admin.ModelAdmin):
    list_display = ('assessment', 'created_by', 'expires_at', 'is_active', 'view_count')
    list_filter = ('is_active', 'expires_at')
    search_fields = ('assessment__user__username', 'token')


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'code', 'awarded_at')
    list_filter = ('code', 'awarded_at')
    search_fields = ('user__username', 'title')

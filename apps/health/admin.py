from django.contrib import admin

from .models import Assessment


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

from django.contrib import admin

from .models import Assessment


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'risk_level', 'risk_score', 'bmi', 'bmi_category', 'created_at')
    list_filter = ('risk_level', 'created_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('risk_score', 'risk_level', 'bmi', 'bmi_category',
                       'findings', 'recommendations', 'created_at')
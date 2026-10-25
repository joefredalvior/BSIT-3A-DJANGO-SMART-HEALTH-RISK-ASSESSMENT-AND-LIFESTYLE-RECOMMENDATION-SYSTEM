from django.contrib import admin

from .models import (
    Appointment,
    CaregiverLink,
    Clinic,
    Medication,
    MentalHealthScreening,
    ReportFeedback,
    SecureMessage,
    VitalReading,
)


@admin.register(VitalReading)
class VitalReadingAdmin(admin.ModelAdmin):
    list_display = ('user', 'measured_at', 'weight_kg', 'systolic', 'diastolic', 'sleep_hours')
    list_filter = ('source', 'measured_at')
    search_fields = ('user__username', 'note')


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('patient', 'clinician', 'scheduled_for', 'status')
    list_filter = ('status', 'scheduled_for')
    search_fields = ('patient__username', 'clinician__username', 'reason')


@admin.register(SecureMessage)
class SecureMessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'recipient', 'subject', 'created_at', 'read_at')
    list_filter = ('created_at',)
    search_fields = ('sender__username', 'recipient__username', 'subject', 'body')


@admin.register(MentalHealthScreening)
class MentalHealthScreeningAdmin(admin.ModelAdmin):
    list_display = ('user', 'kind', 'score', 'severity', 'created_at')
    list_filter = ('kind', 'severity', 'created_at')
    search_fields = ('user__username',)


@admin.register(Medication)
class MedicationAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'dosage', 'frequency', 'is_active', 'reminder_time')
    list_filter = ('is_active',)
    search_fields = ('user__username', 'name')


@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = ('name', 'address', 'phone', 'is_partner')
    list_filter = ('is_partner',)
    search_fields = ('name', 'address', 'services')


@admin.register(ReportFeedback)
class ReportFeedbackAdmin(admin.ModelAdmin):
    list_display = ('user', 'assessment', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('user__username', 'comments')


@admin.register(CaregiverLink)
class CaregiverLinkAdmin(admin.ModelAdmin):
    list_display = ('owner', 'dependent', 'dependent_email', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('owner__username', 'dependent__username', 'dependent_email')

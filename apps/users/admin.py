from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'sex', 'birthdate', 'height_cm', 'activity_level',
                    'family_history', 'conditions', 'updated_at')
    list_filter = ('sex', 'activity_level', 'family_history', 'conditions')
    search_fields = ('user__username', 'user__email')

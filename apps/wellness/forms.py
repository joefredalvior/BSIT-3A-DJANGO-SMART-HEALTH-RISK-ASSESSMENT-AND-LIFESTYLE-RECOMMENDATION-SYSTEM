from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import (
    Appointment,
    CaregiverLink,
    Clinic,
    Medication,
    ReportFeedback,
    SecureMessage,
    VitalReading,
)

User = get_user_model()


class VitalReadingForm(forms.ModelForm):
    class Meta:
        model = VitalReading
        fields = (
            'measured_at', 'weight_kg', 'waist_cm', 'systolic', 'diastolic',
            'sleep_hours', 'exercise_minutes', 'note',
        )
        widgets = {
            'measured_at': forms.DateTimeInput(
                attrs={'class': 'form-control', 'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
            'weight_kg': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'placeholder': 'kg'}),
            'waist_cm': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'cm'}),
            'systolic': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'mmHg'}),
            'diastolic': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'mmHg'}),
            'sleep_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'placeholder': 'hours'}),
            'exercise_minutes': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'minutes'}),
            'note': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional note'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['measured_at'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['measured_at'].initial = timezone.localtime().strftime('%Y-%m-%dT%H:%M')

    def clean(self):
        cleaned = super().clean()
        has_value = any(
            cleaned.get(name) not in (None, '')
            for name in ('weight_kg', 'waist_cm', 'systolic', 'diastolic',
                         'sleep_hours', 'exercise_minutes')
        )
        if not has_value:
            raise forms.ValidationError('Enter at least one measurement.')
        systolic = cleaned.get('systolic')
        diastolic = cleaned.get('diastolic')
        if systolic and diastolic and systolic <= diastolic:
            self.add_error('diastolic', 'Diastolic pressure must be lower than systolic pressure.')
        return cleaned


class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ('clinician', 'scheduled_for', 'duration_minutes', 'reason')
        widgets = {
            'clinician': forms.Select(attrs={'class': 'form-select'}),
            'scheduled_for': forms.DateTimeInput(
                attrs={'class': 'form-control', 'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
            'duration_minutes': forms.Select(
                choices=[(15, '15 minutes'), (30, '30 minutes'), (45, '45 minutes'), (60, '60 minutes')],
                attrs={'class': 'form-select'},
            ),
            'reason': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Reason for visit'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['clinician'].queryset = User.objects.filter(
            is_active=True, is_staff=True,
        ).order_by('first_name', 'username')
        self.fields['clinician'].required = False
        self.fields['clinician'].empty_label = 'First available clinician'
        self.fields['scheduled_for'].input_formats = ['%Y-%m-%dT%H:%M']

    def clean_scheduled_for(self):
        value = self.cleaned_data['scheduled_for']
        if value <= timezone.now():
            raise forms.ValidationError('Choose a date and time in the future.')
        return value


class SecureMessageForm(forms.ModelForm):
    class Meta:
        model = SecureMessage
        fields = ('recipient', 'assessment', 'subject', 'body')
        widgets = {
            'recipient': forms.Select(attrs={'class': 'form-select'}),
            'assessment': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional subject'}),
            'body': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Write your message...'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            recipients = User.objects.filter(is_active=True)
            if not (user.is_staff or user.is_superuser):
                recipients = recipients.filter(is_staff=True)
            self.fields['recipient'].queryset = recipients.exclude(pk=user.pk).order_by('first_name', 'username')
            self.fields['assessment'].queryset = user.assessments.all()
        self.fields['assessment'].required = False
        self.fields['assessment'].empty_label = 'Not linked to an assessment'


class MedicationForm(forms.ModelForm):
    class Meta:
        model = Medication
        fields = (
            'name', 'dosage', 'frequency', 'start_date', 'end_date',
            'reminder_time', 'notes', 'is_active',
        )
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'dosage': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 10 mg'}),
            'frequency': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. once daily'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reminder_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', 'End date must be after the start date.')
        return cleaned


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = ReportFeedback
        fields = ('rating', 'comments')
        widgets = {
            'rating': forms.RadioSelect(choices=[(i, f'{i} star{"s" if i > 1 else ""}') for i in range(1, 6)]),
            'comments': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'What was useful or confusing? (optional)',
            }),
        }


class CaregiverInviteForm(forms.ModelForm):
    class Meta:
        model = CaregiverLink
        fields = ('dependent_email', 'relationship')
        widgets = {
            'dependent_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'their@email.com'}),
            'relationship': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. parent, spouse'}),
        }


class VitalImportForm(forms.Form):
    file = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.csv'}),
    )

    def clean_file(self):
        upload = self.cleaned_data['file']
        if not upload.name.lower().endswith('.csv'):
            raise forms.ValidationError('Upload a CSV file.')
        if upload.size > 2 * 1024 * 1024:
            raise forms.ValidationError('CSV files must be 2 MB or smaller.')
        return upload


class ClinicSearchForm(forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by clinic, address or service',
        }),
    )

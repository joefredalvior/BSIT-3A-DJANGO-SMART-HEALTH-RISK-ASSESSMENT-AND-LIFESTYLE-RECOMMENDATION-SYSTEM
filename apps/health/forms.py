from django import forms

from . import engine
from .models import HealthGoal


class AssessmentForm(forms.Form):
    age = forms.IntegerField(min_value=13, max_value=100)
    sex = forms.ChoiceField(choices=engine.SEX_CHOICES)
    height_cm = forms.IntegerField(min_value=100, max_value=250)
    weight_kg = forms.DecimalField(min_value=30, max_value=300, max_digits=5, decimal_places=1)
    waist_cm = forms.IntegerField(min_value=40, max_value=200)
    systolic = forms.IntegerField(min_value=70, max_value=250)
    diastolic = forms.IntegerField(min_value=40, max_value=150)
    activity_level = forms.ChoiceField(choices=engine.ACTIVITY_LEVELS)
    smoking_status = forms.ChoiceField(choices=engine.SMOKING_STATUS)
    alcohol_status = forms.ChoiceField(choices=engine.ALCOHOL_STATUS)
    diet_quality = forms.ChoiceField(choices=engine.DIET_QUALITY)
    sleep_hours = forms.DecimalField(min_value=0, max_value=16, max_digits=3, decimal_places=1)
    family_history = forms.ChoiceField(choices=engine.FAMILY_HISTORY_CHOICES)
    conditions = forms.ChoiceField(choices=engine.CONDITION_CHOICES)
    stress_level = forms.ChoiceField(choices=engine.STRESS_CHOICES)
    fruit_veg_servings = forms.IntegerField(min_value=0, max_value=15)

    field_order = [
        'age', 'sex', 'height_cm', 'weight_kg', 'waist_cm',
        'systolic', 'diastolic', 'activity_level', 'smoking_status',
        'alcohol_status', 'diet_quality', 'sleep_hours', 'family_history',
        'conditions', 'stress_level', 'fruit_veg_servings',
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.setdefault('class', 'form-control')
        for name in ('sex', 'activity_level', 'smoking_status', 'alcohol_status',
                     'diet_quality', 'family_history', 'conditions', 'stress_level'):
            self.fields[name].widget.attrs['class'] = 'form-select'
        for name, (low, high) in {
            'age': (13, 100),
            'height_cm': (100, 250),
            'weight_kg': (30, 300),
            'waist_cm': (40, 200),
            'systolic': (70, 250),
            'diastolic': (40, 150),
            'sleep_hours': (0, 16),
            'fruit_veg_servings': (0, 15),
        }.items():
            self.fields[name].error_messages['min_value'] = f'Enter a value between {low} and {high}.'
            self.fields[name].error_messages['max_value'] = f'Enter a value between {low} and {high}.'
            self.fields[name].error_messages['required'] = 'This field is required and must be a number.'
        for name in ('sex', 'activity_level', 'smoking_status', 'alcohol_status',
                     'diet_quality', 'family_history', 'conditions', 'stress_level'):
            self.fields[name].error_messages['invalid_choice'] = 'Please select a valid option.'
            self.fields[name].error_messages['required'] = 'Please select a valid option.'

    def clean(self):
        cleaned = super().clean()
        systolic = cleaned.get('systolic')
        diastolic = cleaned.get('diastolic')
        if systolic and diastolic and systolic <= diastolic:
            self.add_error('diastolic', 'Diastolic pressure must be lower than systolic pressure.')
        return cleaned

    def field_errors(self):
        return {
            name: errors[0]
            for name, errors in self.errors.items()
            if errors
        }

    def cleaned_form_data(self):
        """String-friendly dict retained for template redisplay and engine calls."""
        return {name: self.data.get(name, '') for name in self.fields}


class HealthGoalForm(forms.ModelForm):
    class Meta:
        model = HealthGoal
        fields = ['metric', 'label', 'target_value', 'unit', 'due_date']
        widgets = {
            'metric': forms.Select(attrs={'class': 'form-select'}),
            'label': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional label'}),
            'target_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. kg, cm, mmHg'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('unit'):
            cleaned['unit'] = {
                'risk_score': 'points',
                'bmi': 'kg/m2',
                'weight_kg': 'kg',
                'waist_cm': 'cm',
                'systolic': 'mmHg',
                'diastolic': 'mmHg',
                'sleep_hours': 'h',
                'fruit_veg_servings': 'servings',
            }.get(cleaned.get('metric'), '')
        return cleaned


class ClinicianNoteForm(forms.Form):
    note = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 3,
            'placeholder': 'Add a clinical note or follow-up instruction...',
        }),
    )
    follow_up_required = forms.BooleanField(required=False)
    follow_up_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('follow_up_required') and not cleaned.get('follow_up_date'):
            raise forms.ValidationError('Choose a follow-up date when follow-up is required.')
        return cleaned

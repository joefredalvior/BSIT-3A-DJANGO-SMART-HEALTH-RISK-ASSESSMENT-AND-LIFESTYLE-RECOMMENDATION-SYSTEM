import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Avg
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from . import engine
from .models import Assessment

# Bounds used both for form validation and for the HTML input attributes.
FIELD_LIMITS = {
    'age': (13, 100),
    'height_cm': (100, 250),
    'weight_kg': (30, 300),
    'waist_cm': (40, 200),
    'systolic': (70, 250),
    'diastolic': (40, 150),
    'sleep_hours': (0, 16),
}

VALID_CHOICES = {
    'sex': dict(engine.SEX_CHOICES),
    'activity_level': dict(engine.ACTIVITY_LEVELS),
    'smoking_status': dict(engine.SMOKING_STATUS),
    'alcohol_status': dict(engine.ALCOHOL_STATUS),
    'diet_quality': dict(engine.DIET_QUALITY),
}

NUMERIC_FIELDS = list(FIELD_LIMITS)


def _parse_number(raw):
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _validate(form_data):
    """Return a dict of field -> error message for anything invalid."""
    errors = {}

    for field, (low, high) in FIELD_LIMITS.items():
        value = _parse_number(form_data.get(field))
        if value is None:
            errors[field] = 'This field is required and must be a number.'
        elif value < low or value > high:
            errors[field] = f'Enter a value between {low} and {high}.'

    for field, choices in VALID_CHOICES.items():
        if form_data.get(field) not in choices:
            errors[field] = 'Please select a valid option.'

    return errors


def form_context(form_data=None, errors=None):
    """Choice lists plus whichever values should be re-selected on redisplay."""
    context = {
        'sex_choices': engine.SEX_CHOICES,
        'activity_choices': engine.ACTIVITY_LEVELS,
        'smoking_choices': engine.SMOKING_STATUS,
        'alcohol_choices': engine.ALCOHOL_STATUS,
        'diet_choices': engine.DIET_QUALITY,
        'bp_band_choices': engine.BLOOD_PRESSURE_BANDS,
        'limits': FIELD_LIMITS,
        'errors': errors or {},
        'form': form_data or {},
    }
    return context


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def assessment_form(request):
    """Collect health inputs and run the risk engine."""
    if request.method == 'GET':
        return render(request, 'health/assessment_form.html', form_context())

    form_data = {field: request.POST.get(field, '').strip() for field in
                 NUMERIC_FIELDS + list(VALID_CHOICES)}

    errors = _validate(form_data)
    if errors:
        return render(request, 'health/assessment_form.html',
                      form_context(form_data, errors))

    result = engine.assess(
        age=form_data['age'],
        sex=form_data['sex'],
        height_cm=form_data['height_cm'],
        weight_kg=form_data['weight_kg'],
        waist_cm=form_data['waist_cm'],
        systolic=form_data['systolic'],
        diastolic=form_data['diastolic'],
        activity_level=form_data['activity_level'],
        smoking_status=form_data['smoking_status'],
        alcohol_status=form_data['alcohol_status'],
        diet_quality=form_data['diet_quality'],
        sleep_hours=form_data['sleep_hours'],
    )

    record = Assessment.objects.create(
        user=request.user,
        age=form_data['age'],
        sex=form_data['sex'],
        height_cm=form_data['height_cm'],
        weight_kg=form_data['weight_kg'],
        waist_cm=form_data['waist_cm'],
        systolic=form_data['systolic'],
        diastolic=form_data['diastolic'],
        blood_pressure_band=engine.blood_pressure_band(
            form_data['systolic'], form_data['diastolic']),
        activity_level=form_data['activity_level'],
        smoking_status=form_data['smoking_status'],
        alcohol_status=form_data['alcohol_status'],
        diet_quality=form_data['diet_quality'],
        sleep_hours=form_data['sleep_hours'],
        risk_score=result.score,
        risk_level=result.level,
        bmi=result.bmi,
        bmi_category=result.bmi_category,
        findings=json.dumps([{
            'label': f.label,
            'points': f.points,
            'detail': f.detail,
            'advice': f.advice,
        } for f in result.findings]),
        recommendations=json.dumps(result.recommendations),
    )

    messages.success(request, 'Assessment complete. Your health advisory report is ready.')
    return redirect('health:report', pk=record.pk)


@login_required(login_url='login')
def report(request, pk):
    """Show the risk report and lifestyle recommendations for one assessment."""
    record = get_object_or_404(Assessment, pk=pk, user=request.user)
    return render(request, 'health/report.html', {
        'record': record,
        'disclaimer': engine.MEDICAL_DISCLAIMER,
    })


@login_required(login_url='login')
def history(request):
    """All of the signed-in user's past assessments, newest first."""
    records = Assessment.objects.filter(user=request.user)
    latest = records.first()
    stats = records.aggregate(average=Avg('risk_score'))

    trend = [
        {'score': r.risk_score, 'level': r.risk_level, 'date': r.created_at}
        for r in list(reversed(records[:12]))
    ]

    return render(request, 'health/history.html', {
        'records': records,
        'latest': latest,
        'average_score': int(round(stats['average'])) if stats['average'] is not None else None,
        'trend': json.dumps(trend),
    })
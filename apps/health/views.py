from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Avg
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from openpyxl import Workbook

from apps.users.models import UserProfile

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
    'fruit_veg_servings': (0, 15),
}

VALID_CHOICES = {
    'sex': dict(engine.SEX_CHOICES),
    'activity_level': dict(engine.ACTIVITY_LEVELS),
    'smoking_status': dict(engine.SMOKING_STATUS),
    'alcohol_status': dict(engine.ALCOHOL_STATUS),
    'diet_quality': dict(engine.DIET_QUALITY),
    'family_history': dict(engine.FAMILY_HISTORY_CHOICES),
    'conditions': dict(engine.CONDITION_CHOICES),
    'stress_level': dict(engine.STRESS_CHOICES),
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


def _initial_form(user):
    """Prefill the form from the latest assessment, or the user's profile."""
    data = {}
    latest = user.assessments.first()
    if latest is not None:
        for field in NUMERIC_FIELDS + list(VALID_CHOICES):
            data[field] = getattr(latest, field, '')

    profile = UserProfile.objects.filter(user=user).first()
    if profile is not None:
        if not data.get('age'):
            data['age'] = profile.age
        for field in ('sex', 'height_cm', 'activity_level', 'family_history', 'conditions'):
            if not data.get(field) and getattr(profile, field, None):
                data[field] = getattr(profile, field)

    return data


def form_context(form_data=None, errors=None):
    """Choice lists plus whichever values should be re-selected on redisplay."""
    context = {
        'sex_choices': engine.SEX_CHOICES,
        'activity_choices': engine.ACTIVITY_LEVELS,
        'smoking_choices': engine.SMOKING_STATUS,
        'alcohol_choices': engine.ALCOHOL_STATUS,
        'diet_choices': engine.DIET_QUALITY,
        'family_history_choices': engine.FAMILY_HISTORY_CHOICES,
        'condition_choices': engine.CONDITION_CHOICES,
        'stress_choices': engine.STRESS_CHOICES,
        'bp_band_choices': engine.BLOOD_PRESSURE_BANDS,
        'limits': FIELD_LIMITS,
        'errors': errors or {},
        'form': form_data or {},
    }
    return context


def _serialize_findings(result):
    return [
        {
            'key': finding.key,
            'label': finding.label,
            'points': finding.points,
            'max_points': finding.max_points,
            'percentage': finding.percentage,
            'band': finding.band,
            'detail': finding.detail,
            'advice': finding.advice,
            'target': finding.target,
            'category': finding.category,
            'modifiable': finding.modifiable,
        }
        for finding in result.findings
    ]


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def assessment_form(request):
    """Collect health inputs and run the risk engine."""
    if request.method == 'GET':
        return render(request, 'health/assessment_form.html',
                      form_context(_initial_form(request.user)))

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
        family_history=form_data['family_history'],
        conditions=form_data['conditions'],
        stress_level=form_data['stress_level'],
        fruit_veg_servings=form_data['fruit_veg_servings'],
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
        family_history=form_data['family_history'],
        conditions=form_data['conditions'],
        stress_level=form_data['stress_level'],
        fruit_veg_servings=form_data['fruit_veg_servings'],
        engine_version=engine.ENGINE_VERSION,
        risk_score=result.score,
        risk_level=result.level,
        bmi=result.bmi,
        bmi_category=result.bmi_category,
        whtr=result.whtr,
        whtr_category=result.whtr_category,
        age_factor=result.age_factor,
        findings=_serialize_findings(result),
        recommendations=result.recommendations,
        targets=result.targets,
    )

    messages.success(request, 'Assessment complete. Your health advisory report is ready.')
    return redirect('health:report', pk=record.pk)


def _compare(previous, current):
    """Return metric-by-metric deltas against the previous assessment."""
    if previous is None:
        return None

    rows = []

    def add(label, before, after, unit='', lower_is_better=True):
        if before is None or after is None:
            return
        change = float(after) - float(before)
        if abs(change) < 0.05:
            trend = 'same'
        elif (change < 0) == lower_is_better:
            trend = 'better'
        else:
            trend = 'worse'
        rows.append({
            'label': label,
            'before': before,
            'after': after,
            'change': round(change, 1),
            'unit': unit,
            'trend': trend,
        })

    add('Risk score', previous.risk_score, current.risk_score)
    add('BMI', previous.bmi, current.bmi)
    add('Systolic', previous.systolic, current.systolic, ' mmHg')
    add('Diastolic', previous.diastolic, current.diastolic, ' mmHg')
    add('Waist', previous.waist_cm, current.waist_cm, ' cm')
    add('Sleep', previous.sleep_hours, current.sleep_hours, ' h', lower_is_better=False)

    return {'previous': previous, 'rows': rows}


def _trend_payload(user, upto=None, limit=12):
    queryset = Assessment.objects.filter(user=user).order_by('created_at')
    if upto is not None:
        queryset = queryset.filter(created_at__lte=upto)
    records = list(queryset)[-limit:]
    return [
        {
            'date': record.created_at.strftime('%d %b %y'),
            'score': record.risk_score,
            'bmi': float(record.bmi) if record.bmi is not None else None,
            'systolic': record.systolic,
            'diastolic': record.diastolic,
        }
        for record in records
    ]


@login_required(login_url='login')
def report(request, pk):
    """Show the risk report and lifestyle recommendations for one assessment."""
    record = get_object_or_404(Assessment, pk=pk, user=request.user)
    return render(request, 'health/report.html', _report_context(record))


def _report_context(record):
    previous = (
        Assessment.objects
        .filter(user=record.user, created_at__lt=record.created_at)
        .order_by('-created_at')
        .first()
    )
    modifiable_saved = sum(
        rec.get('points_saved', 0)
        for rec in record.recommendation_list
        if rec.get('modifiable', True)
    )
    projected_score = max(
        int(round(record.risk_score - (modifiable_saved / engine.MAX_SCORE) * 100)),
        0,
    )
    return {
        'record': record,
        'disclaimer': engine.MEDICAL_DISCLAIMER,
        'comparison': _compare(previous, record),
        'trend': _trend_payload(record.user, upto=record.created_at),
        'breakdown': record.finding_list,
        'projected_score': projected_score,
    }


@login_required(login_url='login')
def clinician_report(request, pk):
    """Read-only report for staff and superusers, for any patient."""
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied
    record = get_object_or_404(Assessment, pk=pk)
    context = _report_context(record)
    context['clinician_view'] = True
    return render(request, 'health/report.html', context)


@login_required(login_url='login')
def history(request):
    """All of the signed-in user's past assessments, newest first."""
    records = Assessment.objects.filter(user=request.user)
    latest = records.first()
    stats = records.aggregate(average=Avg('risk_score'))

    paginator = Paginator(records, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'health/history.html', {
        'records': page_obj,
        'total_count': paginator.count,
        'latest': latest,
        'average_score': int(round(stats['average'])) if stats['average'] is not None else None,
        'trend': _trend_payload(request.user),
    })


@login_required(login_url='login')
@require_http_methods(['POST'])
def delete_assessment(request, pk):
    """Let a user permanently delete one of their own assessments."""
    record = get_object_or_404(Assessment, pk=pk, user=request.user)
    record.delete()
    messages.success(request, 'Assessment deleted.')
    return redirect('health:history')


@login_required(login_url='login')
def export(request, pk):
    """Download one assessment as an Excel workbook."""
    queryset = Assessment.objects.all()
    if not (request.user.is_staff or request.user.is_superuser):
        queryset = queryset.filter(user=request.user)
    record = get_object_or_404(queryset, pk=pk)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Health report'

    sheet.append(['HealthWise - Health Risk Report'])
    sheet.append(['Generated', record.created_at.strftime('%Y-%m-%d %H:%M')])
    sheet.append(['Engine version', record.engine_version])
    sheet.append([])

    sheet.append(['Risk score', record.risk_score])
    sheet.append(['Risk level', record.risk_level])
    sheet.append(['BMI', record.bmi])
    sheet.append(['BMI category', record.bmi_category])
    sheet.append(['Waist-to-height ratio', record.whtr])
    sheet.append(['Age weighting', record.age_factor])
    sheet.append([])

    sheet.append(['Inputs'])
    for label, value in [
        ('Age', record.age),
        ('Sex', record.get_sex_display()),
        ('Height (cm)', record.height_cm),
        ('Weight (kg)', record.weight_kg),
        ('Waist (cm)', record.waist_cm),
        ('Blood pressure', f'{record.systolic}/{record.diastolic}'),
        ('Activity', record.get_activity_level_display()),
        ('Smoking', record.get_smoking_status_display()),
        ('Alcohol', record.get_alcohol_status_display()),
        ('Diet', record.get_diet_quality_display()),
        ('Sleep (h)', record.sleep_hours),
        ('Family history', record.get_family_history_display()),
        ('Conditions', record.get_conditions_display()),
        ('Stress', record.get_stress_level_display()),
        ('Fruit/veg servings', record.fruit_veg_servings),
    ]:
        sheet.append([label, value])
    sheet.append([])

    sheet.append(['Risk factors'])
    sheet.append(['Factor', 'Points', 'Maximum', 'Band', 'Detail', 'Target'])
    for finding in record.finding_list:
        sheet.append([
            finding.get('label'),
            finding.get('points'),
            finding.get('max_points'),
            finding.get('band'),
            finding.get('detail'),
            finding.get('target'),
        ])
    sheet.append([])

    sheet.append(['Recommendations'])
    sheet.append(['Priority', 'Title', 'Category', 'Points saved', 'Timeframe', 'Target', 'Advice'])
    for rec in record.recommendation_list:
        sheet.append([
            rec.get('priority'),
            rec.get('title'),
            rec.get('category'),
            rec.get('points_saved'),
            rec.get('timeframe'),
            rec.get('target'),
            rec.get('advice'),
        ])
    sheet.append([])
    sheet.append(['Disclaimer', engine.MEDICAL_DISCLAIMER])

    for column in sheet.columns:
        width = max(len(str(cell.value or '')) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(width + 2, 60)

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="health-report-{record.pk}.xlsx"'
    return response

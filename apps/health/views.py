from io import BytesIO
import base64
import json
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from openpyxl import Workbook

from apps.core.security import log_event

from . import engine
from .forms import AssessmentForm, ClinicianNoteForm, HealthGoalForm
from .helpers import (
    compare as _compare,
    form_context,
    goal_progress as _goal_progress,
    initial_form as _initial_form,
    is_clinician as _is_clinician,
    serialize_findings as _serialize_findings,
    trend_payload as _trend_payload,
)
from .models import Assessment, ClinicianNote, HealthGoal, ReportShare
from .pdf import build_report_pdf
from .planner import build_plan
from .services import award_achievements


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def assessment_form(request):
    """Collect health inputs and run the risk engine."""
    if request.method == 'GET':
        return render(request, 'health/assessment_form.html',
                      form_context(_initial_form(request.user)))

    form = AssessmentForm(request.POST)
    if not form.is_valid():
        return render(request, 'health/assessment_form.html',
                      form_context(request.POST, form.field_errors()))

    data = form.cleaned_data
    result = engine.assess(
        age=data['age'],
        sex=data['sex'],
        height_cm=data['height_cm'],
        weight_kg=data['weight_kg'],
        waist_cm=data['waist_cm'],
        systolic=data['systolic'],
        diastolic=data['diastolic'],
        activity_level=data['activity_level'],
        smoking_status=data['smoking_status'],
        alcohol_status=data['alcohol_status'],
        diet_quality=data['diet_quality'],
        sleep_hours=data['sleep_hours'],
        family_history=data['family_history'],
        conditions=data['conditions'],
        stress_level=data['stress_level'],
        fruit_veg_servings=data['fruit_veg_servings'],
    )

    record = Assessment.objects.create(
        user=request.user,
        age=data['age'],
        sex=data['sex'],
        height_cm=data['height_cm'],
        weight_kg=data['weight_kg'],
        waist_cm=data['waist_cm'],
        systolic=data['systolic'],
        diastolic=data['diastolic'],
        blood_pressure_band=engine.blood_pressure_band(
            data['systolic'], data['diastolic']),
        activity_level=data['activity_level'],
        smoking_status=data['smoking_status'],
        alcohol_status=data['alcohol_status'],
        diet_quality=data['diet_quality'],
        sleep_hours=data['sleep_hours'],
        family_history=data['family_history'],
        conditions=data['conditions'],
        stress_level=data['stress_level'],
        fruit_veg_servings=data['fruit_veg_servings'],
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

    log_event(request, 'assessment.created', assessment=record.pk, score=record.risk_score)
    award_achievements(request.user)
    messages.success(request, 'Assessment complete. Your health advisory report is ready.')
    return redirect('health:report', pk=record.pk)


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def goals(request):
    form = HealthGoalForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        goal = form.save(commit=False)
        goal.user = request.user
        goal.save()
        award_achievements(request.user)
        log_event(request, 'goal.created', goal=goal.pk, metric=goal.metric)
        messages.success(request, 'Goal added. It will be tracked against your latest assessment.')
        return redirect('health:goals')

    latest = request.user.assessments.first()
    goal_rows = [
        {'goal': goal, 'progress': _goal_progress(goal, latest)}
        for goal in request.user.health_goals.filter(is_active=True)
    ]
    return render(request, 'health/goals.html', {
        'form': form,
        'goal_rows': goal_rows,
        'latest': latest,
    })


@login_required(login_url='login')
@require_POST
def delete_goal(request, pk):
    goal = get_object_or_404(HealthGoal, pk=pk, user=request.user)
    goal.delete()
    log_event(request, 'goal.deleted', goal=pk)
    messages.success(request, 'Goal removed.')
    return redirect('health:goals')


@login_required(login_url='login')
def report(request, pk):
    """Show the risk report and lifestyle recommendations for one assessment."""
    record = get_object_or_404(Assessment, pk=pk, user=request.user)
    context = _report_context(record)
    context.update({
        'activity_levels': engine.ACTIVITY_LEVELS,
        'smoking_statuses': engine.SMOKING_STATUS,
        'diet_qualities': engine.DIET_QUALITY,
    })
    if context['active_share']:
        share_url = request.build_absolute_uri(
            reverse('health:shared_report', args=[context['active_share'].token])
        )
        context['share_url'] = share_url
        context['share_qr'] = _qr_svg_data_uri(share_url)
    return render(request, 'health/report.html', context)


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
    peer_stats = (
        Assessment.objects
        .filter(
            sex=record.sex,
            age__gte=max(record.age - 10, 13),
            age__lte=record.age + 10,
        )
        .exclude(pk=record.pk)
        .aggregate(average=Avg('risk_score'), count=Count('id'))
    )
    peer_comparison = None
    if peer_stats['count']:
        peer_comparison = {
            'average': int(round(peer_stats['average'])),
            'count': peer_stats['count'],
            'difference': int(round(record.risk_score - peer_stats['average'])),
        }
    active_share = record.shares.filter(
        is_active=True, expires_at__gt=timezone.now(),
    ).first()
    return {
        'record': record,
        'disclaimer': engine.MEDICAL_DISCLAIMER,
        'comparison': _compare(previous, record),
        'trend': _trend_payload(record.user, upto=record.created_at),
        'breakdown': record.finding_list,
        'projected_score': projected_score,
        'notes': record.clinician_notes.select_related('author'),
        'peer_comparison': peer_comparison,
        'user_feedback': record.feedback.filter(user=record.user).first(),
        'active_share': active_share,
        'lifestyle_plan': build_plan(record),
    }


@login_required(login_url='login')
def clinician_report(request, pk):
    """Read-only report for staff and superusers, for any patient."""
    if not _is_clinician(request.user):
        raise PermissionDenied
    record = get_object_or_404(Assessment, pk=pk)
    context = _report_context(record)
    context['clinician_view'] = True
    context['note_form'] = ClinicianNoteForm()
    log_event(request, 'clinician.report_viewed', patient=record.user_id, assessment=record.pk)
    return render(request, 'health/report.html', context)


@login_required(login_url='login')
@user_passes_test(_is_clinician, login_url='dashboard')
@require_POST
def add_clinician_note(request, pk):
    record = get_object_or_404(Assessment, pk=pk)
    form = ClinicianNoteForm(request.POST)
    if form.is_valid():
        note = ClinicianNote.objects.create(
            assessment=record,
            author=request.user,
            note=form.cleaned_data['note'],
            follow_up_required=form.cleaned_data['follow_up_required'],
            follow_up_date=form.cleaned_data.get('follow_up_date'),
        )
        log_event(request, 'clinician.note_added', assessment=record.pk, note=note.pk)
        messages.success(request, 'Clinical note added.')
    else:
        messages.error(request, 'Please add a note and a follow-up date if follow-up is required.')
    return redirect('health:clinician_report', pk=record.pk)


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
@require_POST
def delete_assessment(request, pk):
    """Let a user permanently delete one of their own assessments."""
    record = get_object_or_404(Assessment, pk=pk, user=request.user)
    log_event(request, 'assessment.deleted', assessment=record.pk)
    record.delete()
    messages.success(request, 'Assessment deleted.')
    return redirect('health:history')


@login_required(login_url='login')
@require_POST
def email_report(request, pk):
    queryset = Assessment.objects.all() if _is_clinician(request.user) else Assessment.objects.filter(user=request.user)
    record = get_object_or_404(queryset, pk=pk)
    recipient = record.user.email
    if not recipient:
        messages.error(request, 'This account has no email address on file.')
        return redirect('health:report', pk=record.pk)

    body = render_to_string('emails/report_email.txt', {
        'user': record.user,
        'record': record,
        'protocol': request.scheme,
        'domain': request.get_host(),
    })
    try:
        send_mail(
            f'Your HealthWise report ({record.created_at:%d %b %Y})',
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
        )
    except Exception:
        messages.error(request, 'We could not send the email. Please try again later.')
    else:
        log_event(request, 'report.emailed', assessment=record.pk, recipient=recipient)
        messages.success(request, f'Report sent to {recipient}.')
    return redirect('health:report', pk=record.pk)


@login_required(login_url='login')
def report_pdf(request, pk):
    queryset = Assessment.objects.all() if _is_clinician(request.user) else Assessment.objects.filter(user=request.user)
    record = get_object_or_404(queryset, pk=pk)
    log_event(request, 'report.pdf_downloaded', assessment=record.pk)
    response = HttpResponse(build_report_pdf(record), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="health-report-{record.pk}.pdf"'
    return response


@login_required(login_url='login')
def export(request, pk):
    """Download one assessment as an Excel workbook."""
    queryset = Assessment.objects.all()
    if not _is_clinician(request.user):
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

    log_event(request, 'report.exported', assessment=record.pk)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="health-report-{record.pk}.xlsx"'
    return response


@login_required(login_url='login')
@user_passes_test(_is_clinician, login_url='dashboard')
def clinician_dashboard(request):
    query = request.GET.get('q', '').strip()
    risk_filter = request.GET.get('risk', '').strip()
    assessments = Assessment.objects.select_related('user').prefetch_related('clinician_notes')

    if query:
        assessments = assessments.filter(
            Q(user__username__icontains=query) |
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query)
        )
    if risk_filter in ('Low', 'Moderate', 'High', 'Critical'):
        assessments = assessments.filter(risk_level=risk_filter)

    stats = assessments.aggregate(average=Avg('risk_score'))
    high_risk_count = assessments.filter(risk_level__in=['High', 'Critical']).count()
    risk_counts = {level: 0 for level in ('Low', 'Moderate', 'High', 'Critical')}
    risk_counts.update({
        row['risk_level']: row['count']
        for row in assessments.values('risk_level').annotate(count=Count('id'))
    })
    follow_up_count = ClinicianNote.objects.filter(
        assessment__in=assessments, follow_up_required=True,
    ).values('assessment').distinct().count()

    paginator = Paginator(assessments, 20)
    page = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'users/clinician.html', {
        'assessments': page,
        'query': query,
        'risk_filter': risk_filter,
        'total': assessments.count(),
        'average_score': int(round(stats['average'])) if stats['average'] is not None else None,
        'high_risk_count': high_risk_count,
        'risk_counts': risk_counts,
        'follow_up_count': follow_up_count,
    })


@login_required(login_url='login')
def api_assessments(request):
    """Read-only JSON feed of the signed-in user's assessments."""
    try:
        limit = min(max(int(request.GET.get('limit', 20)), 1), 100)
    except (TypeError, ValueError):
        limit = 20

    records = Assessment.objects.filter(user=request.user)[:limit]
    return JsonResponse({
        'count': Assessment.objects.filter(user=request.user).count(),
        'results': [
            {
                'id': record.pk,
                'created_at': record.created_at.isoformat(),
                'risk_score': record.risk_score,
                'risk_level': record.risk_level,
                'bmi': float(record.bmi) if record.bmi is not None else None,
                'systolic': record.systolic,
                'diastolic': record.diastolic,
                'detail_url': request.build_absolute_uri(
                    reverse('health:api_detail', args=[record.pk])
                ),
            }
            for record in records
        ],
    })


@login_required(login_url='login')
def api_assessment_detail(request, pk):
    record = get_object_or_404(Assessment, pk=pk, user=request.user)
    return JsonResponse({
        'id': record.pk,
        'created_at': record.created_at.isoformat(),
        'engine_version': record.engine_version,
        'risk_score': record.risk_score,
        'risk_level': record.risk_level,
        'summary': record.summary,
        'bmi': float(record.bmi) if record.bmi is not None else None,
        'bmi_category': record.bmi_category,
        'whtr': float(record.whtr) if record.whtr is not None else None,
        'blood_pressure': {'systolic': record.systolic, 'diastolic': record.diastolic},
        'findings': record.finding_list,
        'recommendations': record.recommendation_list,
        'targets': record.target_list,
    })


def _qr_svg_data_uri(value):
    try:
        import qrcode
        import qrcode.image.svg
        image = qrcode.make(
            value,
            image_factory=qrcode.image.svg.SvgPathImage,
            box_size=8,
        )
        buffer = BytesIO()
        image.save(buffer)
        return 'data:image/svg+xml;base64,' + base64.b64encode(buffer.getvalue()).decode()
    except Exception:
        return None


@login_required(login_url='login')
@require_POST
def share_report(request, pk):
    record = get_object_or_404(Assessment, pk=pk, user=request.user)
    share = ReportShare.objects.create(
        assessment=record,
        created_by=request.user,
        expires_at=timezone.now() + timedelta(days=7),
    )
    log_event(request, 'report.shared', assessment=record.pk, share=share.pk)
    messages.success(request, 'A private 7-day report link was created.')
    return redirect('health:report', pk=record.pk)


@login_required(login_url='login')
@require_POST
def revoke_share(request, pk):
    share = get_object_or_404(
        ReportShare, pk=pk, assessment__user=request.user,
    )
    share.is_active = False
    share.save(update_fields=['is_active'])
    log_event(request, 'report.share_revoked', assessment=share.assessment_id)
    messages.success(request, 'Share link revoked.')
    return redirect('health:report', pk=share.assessment_id)


def shared_report(request, token):
    share = get_object_or_404(ReportShare, token=token)
    if not share.is_valid:
        return render(request, 'health/shared_report.html', {
            'invalid': True,
            'share': share,
        }, status=410)

    if request.method == 'POST':
        return HttpResponse(status=405)

    ReportShare.objects.filter(pk=share.pk).update(view_count=share.view_count + 1)
    context = _report_context(share.assessment)
    context.update({
        'share': share,
        'shared_view': True,
        'record': share.assessment,
    })
    return render(request, 'health/shared_report.html', context)


@login_required(login_url='login')
@require_POST
def simulate(request):
    try:
        payload = json.loads(request.body or '{}')
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)

    record = get_object_or_404(Assessment, pk=payload.get('assessment'), user=request.user)
    values = {
        'age': record.age,
        'sex': record.sex,
        'height_cm': record.height_cm,
        'weight_kg': record.weight_kg,
        'waist_cm': record.waist_cm,
        'systolic': record.systolic,
        'diastolic': record.diastolic,
        'activity_level': record.activity_level,
        'smoking_status': record.smoking_status,
        'alcohol_status': record.alcohol_status,
        'diet_quality': record.diet_quality,
        'sleep_hours': record.sleep_hours,
        'family_history': record.family_history,
        'conditions': record.conditions,
        'stress_level': record.stress_level,
        'fruit_veg_servings': record.fruit_veg_servings,
    }
    numeric_bounds = {
        'weight_kg': (30, 300),
        'waist_cm': (40, 200),
        'systolic': (70, 250),
        'diastolic': (40, 150),
        'sleep_hours': (0, 16),
        'fruit_veg_servings': (0, 15),
    }
    choices = {
        'activity_level': dict(engine.ACTIVITY_LEVELS),
        'smoking_status': dict(engine.SMOKING_STATUS),
        'diet_quality': dict(engine.DIET_QUALITY),
    }
    for field, (low, high) in numeric_bounds.items():
        if field in payload:
            try:
                number = float(payload[field])
            except (TypeError, ValueError):
                return JsonResponse({'error': f'Invalid value for {field}.'}, status=400)
            if number < low or number > high:
                return JsonResponse({'error': f'{field} must be between {low} and {high}.'}, status=400)
            values[field] = number
    for field, allowed in choices.items():
        if field in payload:
            if payload[field] not in allowed:
                return JsonResponse({'error': f'Invalid option for {field}.'}, status=400)
            values[field] = payload[field]

    if values['systolic'] <= values['diastolic']:
        return JsonResponse({'error': 'Systolic must be higher than diastolic.'}, status=400)

    result = engine.assess(**values)
    return JsonResponse({
        'score': result.score,
        'level': result.level,
        'delta': result.score - record.risk_score,
        'bmi': result.bmi,
        'bmi_category': result.bmi_category,
        'summary': engine.LEVEL_SUMMARY.get(result.level, ''),
        'row': {
            'systolic': values['systolic'],
            'diastolic': values['diastolic'],
            'weight_kg': values['weight_kg'],
            'activity_level': values['activity_level'],
            'smoking_status': values['smoking_status'],
        },
    })

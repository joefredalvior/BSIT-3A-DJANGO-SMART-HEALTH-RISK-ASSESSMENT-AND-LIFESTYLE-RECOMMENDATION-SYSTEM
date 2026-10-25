import csv
import io
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.security import log_event
from apps.health.models import Assessment
from apps.health.services import BADGES, award_achievements
from apps.health.views import _report_context

from . import mental_health
from .forms import (
    AppointmentForm,
    CaregiverInviteForm,
    ClinicSearchForm,
    FeedbackForm,
    MedicationForm,
    SecureMessageForm,
    VitalImportForm,
    VitalReadingForm,
)
from .helpers import (
    is_clinician as _is_clinician,
    vitals_payload as _vitals_payload,
)
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


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def vitals(request):
    form = VitalReadingForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        reading = form.save(commit=False)
        reading.user = request.user
        reading.save()
        award_achievements(request.user)
        log_event(request, 'vitals.created', reading=reading.pk)
        messages.success(request, 'Vital reading saved.')
        return redirect('wellness:vitals')

    readings = request.user.vital_readings.select_related('user')[:30]
    latest = readings[0] if readings else None
    return render(request, 'wellness/vitals.html', {
        'form': form,
        'readings': readings,
        'latest': latest,
        'chart': _vitals_payload(request.user),
        'import_form': VitalImportForm(),
    })


@login_required(login_url='login')
@require_POST
def delete_vital(request, pk):
    reading = get_object_or_404(VitalReading, pk=pk, user=request.user)
    reading.delete()
    log_event(request, 'vitals.deleted', reading=pk)
    messages.success(request, 'Vital reading removed.')
    return redirect('wellness:vitals')


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def import_vitals(request):
    if request.method == 'GET':
        return redirect('wellness:vitals')

    form = VitalImportForm(request.POST, request.FILES)
    if not form.is_valid():
        for error in form.errors.values():
            messages.error(request, error[0])
        return redirect('wellness:vitals')

    raw = form.cleaned_data['file'].read()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('latin-1')

    reader = csv.DictReader(io.StringIO(text))
    headers = {h.strip().lower() for h in (reader.fieldnames or [])}
    if not headers or not ({'date', 'measured_at'} & headers):
        messages.error(request, 'CSV needs a date column (date or measured_at).')
        return redirect('wellness:vitals')

    created = 0
    errors = 0
    for row in reader:
        row = {str(k).strip().lower(): (v or '').strip() for k, v in row.items()}
        raw_date = row.get('date') or row.get('measured_at')
        measured = parse_datetime(raw_date) if raw_date else None
        if measured is None and raw_date:
            parsed_date = parse_date(raw_date)
            if parsed_date:
                measured = datetime.combine(parsed_date, datetime.min.time())
        if measured is None:
            errors += 1
            continue
        if timezone.is_naive(measured):
            measured = timezone.make_aware(measured, timezone.get_current_timezone())

        def number(key):
            value = row.get(key)
            try:
                return float(value) if value not in (None, '') else None
            except (TypeError, ValueError):
                return None

        reading = VitalReading(
            user=request.user,
            measured_at=measured,
            weight_kg=number('weight') or number('weight_kg'),
            waist_cm=number('waist') or number('waist_cm'),
            systolic=number('systolic'),
            diastolic=number('diastolic'),
            sleep_hours=number('sleep') or number('sleep_hours'),
            exercise_minutes=number('exercise') or number('exercise_minutes'),
            note=row.get('note', '')[:200],
            source='import',
        )
        try:
            reading.full_clean()
            reading.save()
            created += 1
        except Exception:
            errors += 1

    if created:
        award_achievements(request.user)
        log_event(request, 'vitals.imported', created=created, errors=errors)
        messages.success(request, f'Imported {created} vital reading{"s" if created != 1 else ""}.')
    if errors:
        messages.warning(request, f'{errors} row{"s" if errors != 1 else ""} could not be imported.')
    return redirect('wellness:vitals')


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def appointments(request):
    form = AppointmentForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        appointment = form.save(commit=False)
        appointment.patient = request.user
        appointment.status = 'requested'
        appointment.save()
        award_achievements(request.user)
        log_event(request, 'appointment.requested', appointment=appointment.pk)
        messages.success(request, 'Appointment requested. The clinic will confirm it.')
        return redirect('wellness:appointments')

    upcoming = request.user.appointments.filter(
        scheduled_for__gte=timezone.now(),
    ).exclude(status='cancelled')[:20]
    past = request.user.appointments.filter(
        scheduled_for__lt=timezone.now(),
    )[:10]
    return render(request, 'wellness/appointments.html', {
        'form': form,
        'upcoming': upcoming,
        'past': past,
    })


@login_required(login_url='login')
@require_POST
def cancel_appointment(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk, patient=request.user)
    if appointment.status not in ('completed', 'cancelled'):
        appointment.status = 'cancelled'
        appointment.save(update_fields=['status', 'updated_at'])
        log_event(request, 'appointment.cancelled', appointment=pk)
        messages.success(request, 'Appointment cancelled.')
    return redirect('wellness:appointments')


@login_required(login_url='login')
@user_passes_test(_is_clinician, login_url='dashboard')
@require_http_methods(['GET', 'POST'])
def clinician_appointments(request):
    if request.method == 'POST':
        appointment = get_object_or_404(
            Appointment, pk=request.POST.get('appointment_id'), clinician=request.user,
        )
        new_status = request.POST.get('status')
        if new_status in dict(Appointment.STATUS_CHOICES):
            appointment.status = new_status
            notes = request.POST.get('notes', '').strip()
            if notes:
                appointment.notes = notes
            appointment.save(update_fields=['status', 'notes', 'updated_at'])
            log_event(request, 'appointment.status_changed', appointment=appointment.pk, status=new_status)
            messages.success(request, 'Appointment updated.')
        return redirect('wellness:clinician_appointments')

    status_filter = request.GET.get('status', '').strip()
    queryset = Appointment.objects.select_related('patient', 'clinician')
    if not request.user.is_superuser:
        queryset = queryset.filter(Q(clinician=request.user) | Q(clinician__isnull=True))
    if status_filter in dict(Appointment.STATUS_CHOICES):
        queryset = queryset.filter(status=status_filter)
    return render(request, 'wellness/clinician_appointments.html', {
        'appointments': queryset[:100],
        'status_filter': status_filter,
        'status_choices': Appointment.STATUS_CHOICES,
    })


@login_required(login_url='login')
def inbox(request):
    received = request.user.received_secure_messages.select_related('sender')
    sent = request.user.sent_secure_messages.select_related('recipient')
    return render(request, 'wellness/inbox.html', {
        'received': received[:50],
        'sent': sent[:50],
        'unread_count': received.filter(read_at__isnull=True).count(),
    })


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def compose_message(request):
    form = SecureMessageForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        message = form.save(commit=False)
        message.sender = request.user
        message.save()
        log_event(request, 'message.sent', message=message.pk, recipient=message.recipient_id)
        messages.success(request, 'Message sent securely.')
        return redirect('wellness:inbox')

    return render(request, 'wellness/compose_message.html', {
        'form': form,
    })


@login_required(login_url='login')
def message_detail(request, pk):
    message = get_object_or_404(
        SecureMessage.objects.select_related('sender', 'recipient'),
        Q(sender=request.user) | Q(recipient=request.user),
        pk=pk,
    )
    if message.recipient == request.user and message.read_at is None:
        message.read_at = timezone.now()
        message.save(update_fields=['read_at'])
    return render(request, 'wellness/message_detail.html', {'message': message})


@login_required(login_url='login')
@require_POST
def reply_message(request, pk):
    original = get_object_or_404(
        SecureMessage, Q(sender=request.user) | Q(recipient=request.user), pk=pk,
    )
    body = request.POST.get('body', '').strip()
    if body:
        SecureMessage.objects.create(
            sender=request.user,
            recipient=original.sender if original.recipient == request.user else original.recipient,
            subject=f'Re: {original.subject}' if original.subject else '',
            body=body,
            assessment=original.assessment,
        )
        log_event(request, 'message.replied', message=original.pk)
        messages.success(request, 'Reply sent.')
    else:
        messages.error(request, 'Write a reply first.')
    return redirect('wellness:message_detail', pk=original.pk)


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def screenings(request):
    kind = request.GET.get('kind', 'phq9')
    if kind not in mental_health.SCREENINGS:
        kind = 'phq9'
    config = mental_health.SCREENINGS[kind]

    if request.method == 'POST':
        kind = request.POST.get('kind', 'phq9')
        if kind not in mental_health.SCREENINGS:
            messages.error(request, 'Choose a valid screening.')
            return redirect('wellness:screenings')
        config = mental_health.SCREENINGS[kind]
        answers = request.POST.getlist('answer')
        if len(answers) != len(config['questions']):
            messages.error(request, 'Please answer every question.')
        else:
            try:
                values = [int(value) for value in answers]
            except (TypeError, ValueError):
                values = []
            if any(value not in (0, 1, 2, 3) for value in values) or not values:
                messages.error(request, 'Answers must be between 0 and 3.')
            else:
                score = sum(values)
                severity = mental_health.severity_for(kind, score)
                screening = MentalHealthScreening.objects.create(
                    user=request.user,
                    kind=kind,
                    answers=values,
                    score=score,
                    severity=severity,
                )
                award_achievements(request.user)
                log_event(request, 'screening.completed', screening=screening.pk, kind=kind)
                messages.success(request, 'Screening complete. This is not a diagnosis.')
                return redirect('wellness:screening_detail', pk=screening.pk)

    history = request.user.mental_health_screenings.all()[:10]
    return render(request, 'wellness/screenings.html', {
        'kind': kind,
        'config': config,
        'questions': config['questions'],
        'answer_choices': mental_health.ANSWER_CHOICES,
        'history': history,
    })


@login_required(login_url='login')
def screening_detail(request, pk):
    screening = get_object_or_404(
        MentalHealthScreening, pk=pk, user=request.user,
    )
    guidance = mental_health.guidance_for(screening.kind, screening.severity)
    questions = mental_health.SCREENINGS[screening.kind]['questions']
    answers = list(zip(questions, screening.answers))
    return render(request, 'wellness/screening_detail.html', {
        'screening': screening,
        'guidance': guidance,
        'answers': answers,
    })


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def medications(request):
    form = MedicationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        medication = form.save(commit=False)
        medication.user = request.user
        medication.save()
        log_event(request, 'medication.created', medication=medication.pk)
        messages.success(request, 'Medication saved.')
        return redirect('wellness:medications')

    active = request.user.medications.filter(is_active=True)
    inactive = request.user.medications.filter(is_active=False)
    return render(request, 'wellness/medications.html', {
        'form': form,
        'active': active,
        'inactive': inactive,
        'now': timezone.localtime(),
    })


@login_required(login_url='login')
@require_POST
def toggle_medication(request, pk):
    medication = get_object_or_404(Medication, pk=pk, user=request.user)
    medication.is_active = not medication.is_active
    medication.save(update_fields=['is_active', 'updated_at'])
    log_event(request, 'medication.toggled', medication=pk, active=medication.is_active)
    return redirect('wellness:medications')


@login_required(login_url='login')
@require_POST
def delete_medication(request, pk):
    medication = get_object_or_404(Medication, pk=pk, user=request.user)
    medication.delete()
    log_event(request, 'medication.deleted', medication=pk)
    messages.success(request, 'Medication removed.')
    return redirect('wellness:medications')


@login_required(login_url='login')
def clinics(request):
    form = ClinicSearchForm(request.GET or None)
    queryset = Clinic.objects.all()
    query = request.GET.get('q', '').strip()
    if query:
        queryset = queryset.filter(
            Q(name__icontains=query) |
            Q(address__icontains=query) |
            Q(services__icontains=query)
        )
    return render(request, 'wellness/clinics.html', {
        'form': form,
        'clinics': queryset,
        'query': query,
    })


@login_required(login_url='login')
@require_POST
def submit_feedback(request, pk):
    assessment = get_object_or_404(Assessment, pk=pk, user=request.user)
    form = FeedbackForm(request.POST)
    if form.is_valid():
        feedback, created = ReportFeedback.objects.update_or_create(
            assessment=assessment,
            user=request.user,
            defaults={
                'rating': form.cleaned_data['rating'],
                'comments': form.cleaned_data['comments'],
            },
        )
        log_event(request, 'report.feedback', assessment=assessment.pk, rating=feedback.rating)
        messages.success(
            request,
            'Thank you. Your feedback was saved.' if created else 'Thank you. Your feedback was updated.',
        )
    else:
        messages.error(request, 'Choose a rating from 1 to 5 stars.')
    return redirect('health:report', pk=assessment.pk)


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def caregivers(request):
    form = CaregiverInviteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        link = form.save(commit=False)
        link.owner = request.user
        link.save()
        accept_url = request.build_absolute_uri(
            reverse('wellness:caregiver_accept', args=[link.token])
        )
        body = render_to_string('emails/caregiver_invite.txt', {
            'owner': request.user,
            'link': link,
            'accept_url': accept_url,
        })
        try:
            send_mail(
                f'{request.user.get_full_name() or request.user.username} invited you to HealthWise',
                body,
                settings.DEFAULT_FROM_EMAIL,
                [link.dependent_email],
            )
        except Exception:
            messages.warning(request, 'Invite saved, but the email could not be sent.')
        else:
            messages.success(request, 'Caregiver invite sent.')
        log_event(request, 'caregiver.invited', link=link.pk)
        return redirect('wellness:caregivers')

    outgoing = request.user.caregiver_links.select_related('dependent')
    incoming = request.user.caregiver_access.select_related('owner')
    return render(request, 'wellness/caregivers.html', {
        'form': form,
        'outgoing': outgoing,
        'incoming': incoming,
    })


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def caregiver_accept(request, token):
    link = get_object_or_404(CaregiverLink, token=token, status='pending')
    email_matches = (request.user.email or '').lower() == link.dependent_email.lower()
    if request.method == 'POST':
        if not email_matches:
            messages.error(request, 'This invite was sent to a different email address.')
            return redirect('wellness:caregivers')
        link.dependent = request.user
        link.status = 'accepted'
        link.accepted_at = timezone.now()
        link.save(update_fields=['dependent', 'status', 'accepted_at'])
        log_event(request, 'caregiver.accepted', link=link.pk)
        messages.success(request, 'Caregiver access accepted.')
        return redirect('wellness:caregivers')

    return render(request, 'wellness/caregiver_accept.html', {
        'link': link,
        'email_matches': email_matches,
    })


@login_required(login_url='login')
@require_POST
def caregiver_revoke(request, pk):
    link = get_object_or_404(
        CaregiverLink.objects.filter(Q(owner=request.user) | Q(dependent=request.user)),
        pk=pk,
    )
    link.status = 'revoked'
    link.save(update_fields=['status'])
    log_event(request, 'caregiver.revoked', link=link.pk)
    messages.success(request, 'Caregiver access revoked.')
    return redirect('wellness:caregivers')


@login_required(login_url='login')
def caregiver_dashboard(request):
    links = request.user.caregiver_links.filter(
        status='accepted', dependent__isnull=False,
    ).select_related('dependent')
    dependents = []
    for link in links:
        dependents.append({
            'link': link,
            'user': link.dependent,
            'assessments': link.dependent.assessments.all()[:5],
        })
    return render(request, 'wellness/caregiver_dashboard.html', {
        'dependents': dependents,
    })


@login_required(login_url='login')
def caregiver_report(request, pk, assessment_pk):
    link = get_object_or_404(
        CaregiverLink,
        pk=pk,
        owner=request.user,
        status='accepted',
        dependent__isnull=False,
    )
    record = get_object_or_404(
        Assessment, pk=assessment_pk, user=link.dependent,
    )
    context = _report_context(record)
    context['caregiver_view'] = True
    context['caregiver_link'] = link
    log_event(request, 'caregiver.report_viewed', assessment=record.pk, link=link.pk)
    return render(request, 'health/report.html', context)


@login_required(login_url='login')
def achievements(request):
    award_achievements(request.user)
    earned = {item.code: item for item in request.user.achievements.all()}
    badges = []
    for code, (title, description, icon) in BADGES.items():
        item = earned.get(code)
        badges.append({
            'code': code,
            'title': title,
            'description': description,
            'icon': icon,
            'earned': item is not None,
            'awarded_at': item.awarded_at if item else None,
        })
    return render(request, 'wellness/achievements.html', {
        'badges': badges,
        'earned_count': len(earned),
    })

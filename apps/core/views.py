import csv
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import (
    PasswordChangeDoneView,
    PasswordChangeView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from apps.health.models import Assessment, HealthGoal
from apps.health.services import award_achievements
from apps.users.models import UserProfile
from apps.users.two_factor import consume_backup_code, verify_code

from .emails import send_verification_email
from .models import AuditEvent, UserSession
from .security import (
    clear_failures,
    client_ip,
    get_lock_state,
    log_event,
    register_failure,
    registration_allowed,
)
from .session_security import mark_session_authenticated
from .tokens import read_verification_token
from .view_helpers import (
    ensure_profile as _ensure_profile,
    validate_registration_data as _validate_registration_data,
)

User = get_user_model()

INVALID_LOGIN_MESSAGE = 'Invalid username or password.'
LOCKED_MESSAGE = 'Too many failed attempts. Please try again later.'


@require_http_methods(['GET', 'POST'])
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'GET':
        return render(request, 'auth/login.html')

    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')
    ip_address = client_ip(request)

    remaining = get_lock_state(username, ip_address)
    if remaining is not None:
        messages.error(request, f'Too many failed attempts. Try again in {remaining} seconds.')
        return render(request, 'auth/login.html', {'locked': True, 'remaining': remaining})

    user = authenticate(request, username=username, password=password)

    if user is not None:
        clear_failures(username, ip_address)
        profile = _ensure_profile(user, verified_default=True)
        if not profile.email_verified:
            messages.warning(
                request,
                'Your email address is not verified yet. '
                'Check your inbox or resend the verification email from your profile.',
            )
        two_factor = getattr(user, 'two_factor', None)
        if two_factor is not None and two_factor.enabled:
            request.session['pending_2fa_user'] = user.pk
            request.session['pending_2fa_attempts'] = 0
            log_event(request, 'login.password_ok', user=user)
            return redirect('two_factor_challenge')
        login(request, user)
        mark_session_authenticated(request)
        log_event(request, 'login.success', user=user)
        return redirect('dashboard')

    attempts_left = register_failure(username, ip_address)
    if attempts_left == 0:
        log_event(request, 'login.locked', username=username)
        remaining = get_lock_state(username, ip_address) or 1
        messages.error(request, LOCKED_MESSAGE)
        return render(request, 'auth/login.html', {'locked': True, 'remaining': remaining})

    log_event(request, 'login.failed', username=username, attempts_left=attempts_left)
    messages.error(
        request,
        f'{INVALID_LOGIN_MESSAGE} {attempts_left} attempt'
        f'{"s" if attempts_left != 1 else ""} remaining.',
    )
    return render(request, 'auth/login.html')


def logout_view(request):
    if request.user.is_authenticated:
        log_event(request, 'logout')
        if request.session.session_key:
            UserSession.objects.filter(
                session_key=request.session.session_key,
            ).update(ended_at=timezone.now())
    logout(request)
    return redirect('login')


@login_required(login_url='login')
def home(request):
    assessments = Assessment.objects.filter(user=request.user)
    latest = assessments.first()
    award_achievements(request.user)

    return render(request, 'home.html', {
        'latest': latest,
        'assessment_count': assessments.count(),
        'has_assessment': latest is not None,
        'record_recent': assessments[:5],
        'goals': request.user.health_goals.filter(is_active=True)[:4],
        'achievements': request.user.achievements.all()[:4],
        'vitals_latest': request.user.vital_readings.first(),
    })


@require_http_methods(['GET', 'POST'])
def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'GET':
        return render(request, 'auth/register.html')

    ip_address = client_ip(request)
    if not registration_allowed(ip_address):
        messages.error(request, 'Too many accounts created from this network. Please try later.')
        return render(request, 'auth/register.html', status=429)

    form_data = {
        'username': request.POST.get('username', ''),
        'first_name': request.POST.get('first_name', ''),
        'last_name': request.POST.get('last_name', ''),
        'email': request.POST.get('email', ''),
        'password': request.POST.get('password', ''),
        'confirm_password': request.POST.get('confirm_password', ''),
        'consent': request.POST.get('consent'),
    }

    errors = _validate_registration_data(form_data)
    if errors:
        return render(request, 'auth/register.html', {'errors': errors, 'form_data': form_data})

    user = User.objects.create_user(
        username=form_data['username'].strip(),
        first_name=form_data['first_name'].strip(),
        last_name=form_data['last_name'].strip(),
        email=form_data['email'].strip(),
        password=form_data['password'],
    )
    UserProfile.objects.create(
        user=user,
        consent_at=timezone.now(),
        consent_version=getattr(settings, 'PRIVACY_VERSION', '1.0'),
    )

    log_event(request, 'account.registered', user=user)
    sent = send_verification_email(request, user)
    login(request, user)
    mark_session_authenticated(request)
    if sent:
        messages.info(request, 'Welcome! We sent a verification link to your email address.')
    else:
        messages.warning(
            request,
            'Your account was created, but the verification email could not be sent. '
            'You can resend it from your profile.',
        )
    return redirect('dashboard')


@require_http_methods(['GET'])
def privacy_policy(request):
    return render(request, 'auth/privacy.html', {
        'privacy_version': getattr(settings, 'PRIVACY_VERSION', '1.0'),
    })


@require_http_methods(['GET'])
def verify_email(request, token):
    payload = read_verification_token(token)
    if payload is None:
        messages.error(request, 'This verification link is invalid or has expired.')
        return render(request, 'auth/verify_email.html', {'verified': False}, status=400)

    user = User.objects.filter(pk=payload.get('uid')).first()
    if user is None or user.email.lower() != str(payload.get('email', '')).lower():
        messages.error(request, 'This verification link is not valid for any account.')
        return render(request, 'auth/verify_email.html', {'verified': False}, status=400)

    profile = _ensure_profile(user)
    if not profile.email_verified:
        profile.email_verified = True
        profile.email_verified_at = timezone.now()
        profile.save(update_fields=['email_verified', 'email_verified_at', 'updated_at'])
        log_event(request, 'account.email_verified', user=user)
        messages.success(request, 'Email verified. Thank you!')
    else:
        messages.info(request, 'Your email address is already verified.')

    if request.user.is_authenticated and request.user.pk == user.pk:
        return redirect('dashboard')
    return redirect('login')


@login_required(login_url='login')
@require_POST
def resend_verification(request):
    profile = _ensure_profile(request.user)
    if profile.email_verified:
        messages.info(request, 'Your email address is already verified.')
        return redirect('users:profile')
    if not request.user.email:
        messages.error(request, 'Add an email address to your account before verifying it.')
        return redirect('users:profile')
    if send_verification_email(request, request.user):
        log_event(request, 'account.verification_resent')
        messages.success(request, 'Verification email sent. Check your inbox.')
    else:
        messages.error(request, 'We could not send the verification email. Please try again later.')
    return redirect('users:profile')


@login_required(login_url='login')
def account_export(request):
    """Download every piece of personal data held for the signed-in user."""
    profile = _ensure_profile(request.user)
    assessments = Assessment.objects.filter(user=request.user)

    records = []
    for record in assessments:
        records.append({
            'id': record.pk,
            'created_at': record.created_at,
            'risk_score': record.risk_score,
            'risk_level': record.risk_level,
            'engine_version': record.engine_version,
            'inputs': {
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
            },
            'outputs': {
                'bmi': record.bmi,
                'bmi_category': record.bmi_category,
                'whtr': record.whtr,
                'findings': record.finding_list,
                'recommendations': record.recommendation_list,
                'targets': record.target_list,
            },
        })

    payload = {
        'exported_at': timezone.now(),
        'account': {
            'username': request.user.username,
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'email': request.user.email,
            'date_joined': request.user.date_joined,
            'last_login': request.user.last_login,
        },
        'profile': {
            'birthdate': profile.birthdate,
            'sex': profile.sex,
            'height_cm': profile.height_cm,
            'activity_level': profile.activity_level,
            'family_history': profile.family_history,
            'conditions': profile.conditions,
            'email_verified': profile.email_verified,
            'consent_at': profile.consent_at,
            'consent_version': profile.consent_version,
        },
        'assessments': records,
        'goals': list(HealthGoal.objects.filter(user=request.user).values(
            'metric', 'label', 'target_value', 'unit', 'due_date', 'is_active', 'created_at',
        )),
    }

    log_event(request, 'account.data_exported')
    response = HttpResponse(
        json.dumps(payload, indent=2, default=str),
        content_type='application/json',
    )
    response['Content-Disposition'] = (
        f'attachment; filename="healthwise-data-{request.user.username}.json"'
    )
    return response


@login_required(login_url='login')
@require_POST
def account_delete(request):
    password = request.POST.get('password', '')
    if not request.user.check_password(password):
        messages.error(request, 'Password is incorrect. Your account was not deleted.')
        return redirect('users:profile')

    if request.user.is_superuser and User.objects.filter(is_superuser=True).count() <= 1:
        messages.error(request, 'You cannot delete the only administrator account.')
        return redirect('users:profile')

    log_event(request, 'account.deleted', username=request.user.username)
    user = request.user
    logout(request)
    user.delete()
    messages.success(request, 'Your account and all associated health data have been deleted.')
    return redirect('login')


class HealthWisePasswordResetView(PasswordResetView):
    template_name = 'auth/password_reset_form.html'
    email_template_name = 'emails/password_reset_email.txt'
    subject_template_name = 'emails/password_reset_subject.txt'
    success_url = reverse_lazy('password_reset_done')


class HealthWisePasswordResetDoneView(PasswordResetDoneView):
    template_name = 'auth/password_reset_done.html'


class HealthWisePasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'auth/password_reset_confirm.html'
    success_url = reverse_lazy('password_reset_complete')


class HealthWisePasswordResetCompleteView(PasswordResetCompleteView):
    template_name = 'auth/password_reset_complete.html'


class HealthWisePasswordChangeView(PasswordChangeView):
    template_name = 'auth/password_change_form.html'
    success_url = reverse_lazy('users:profile')

    def form_valid(self, form):
        log_event(self.request, 'account.password_changed')
        messages.success(self.request, 'Your password has been updated.')
        return super().form_valid(form)


class HealthWisePasswordChangeDoneView(PasswordChangeDoneView):
    template_name = 'auth/password_change_done.html'


def healthz(request):
    """Unauthenticated readiness probe used by hosting platforms."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception:
        return JsonResponse({'status': 'error', 'database': 'unavailable'}, status=503)
    return JsonResponse({'status': 'ok', 'database': 'ok'})


@require_http_methods(['GET', 'POST'])
def two_factor_challenge(request):
    user_id = request.session.get('pending_2fa_user')
    if not user_id:
        return redirect('login')
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        request.session.pop('pending_2fa_user', None)
        return redirect('login')

    if request.method == 'POST':
        settings_obj = getattr(user, 'two_factor', None)
        code = request.POST.get('code', '').strip()
        valid = False
        if settings_obj is not None and settings_obj.enabled:
            valid = verify_code(settings_obj.secret, code) or consume_backup_code(settings_obj, code)
        if valid:
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            mark_session_authenticated(request)
            request.session.pop('pending_2fa_user', None)
            request.session.pop('pending_2fa_attempts', None)
            log_event(request, 'login.2fa_success', user=user)
            return redirect('dashboard')
        attempts = request.session.get('pending_2fa_attempts', 0) + 1
        request.session['pending_2fa_attempts'] = attempts
        if attempts >= 5:
            request.session.pop('pending_2fa_user', None)
            messages.error(request, 'Too many incorrect codes. Please sign in again.')
            return redirect('login')
        messages.error(request, 'That code is not valid. Try again.')

    return render(request, 'auth/two_factor_challenge.html')


@require_http_methods(['GET'])
def set_language(request, lang):
    if lang in ('en', 'fil'):
        request.session['ui_language'] = lang
    next_url = request.GET.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect('dashboard')


@user_passes_test(lambda user: user.is_staff or user.is_superuser)
def audit_log(request):
    events = AuditEvent.objects.select_related('user')
    query = request.GET.get('q', '').strip()
    action = request.GET.get('action', '').strip()
    date_from = request.GET.get('from', '').strip()
    date_to = request.GET.get('to', '').strip()
    if query:
        events = events.filter(
            Q(user__username__icontains=query) |
            Q(ip_address__icontains=query) |
            Q(action__icontains=query)
        )
    if action:
        events = events.filter(action=action)
    parsed_from = parse_date(date_from) if date_from else None
    parsed_to = parse_date(date_to) if date_to else None
    if parsed_from:
        events = events.filter(created_at__date__gte=parsed_from)
    if parsed_to:
        events = events.filter(created_at__date__lte=parsed_to)
    paginator = Paginator(events, 40)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'core/audit_log.html', {
        'events': page,
        'query': query,
        'action': action,
        'date_from': date_from,
        'date_to': date_to,
        'actions': AuditEvent.objects.values_list('action', flat=True).distinct().order_by('action'),
    })


@user_passes_test(lambda user: user.is_staff or user.is_superuser)
def audit_log_export(request):
    events = AuditEvent.objects.select_related('user')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="audit-log.csv"'
    writer = csv.writer(response)
    writer.writerow(['created_at', 'action', 'user', 'ip_address', 'metadata'])
    for event in events[:10000]:
        writer.writerow([
            event.created_at.isoformat(),
            event.action,
            event.user.get_username() if event.user else '',
            event.ip_address or '',
            json.dumps(event.metadata, default=str),
        ])
    return response


@require_http_methods(['GET'])
def manifest(request):
    response = JsonResponse({
        'name': 'HealthWise - Health Risk Assessment',
        'short_name': 'HealthWise',
        'description': 'Screen your health risk and track healthy lifestyle changes.',
        'start_url': '/home/',
        'display': 'standalone',
        'background_color': '#f6f8fb',
        'theme_color': '#0f766e',
        'icons': [
            {'src': '/static/icons/icon-192.svg', 'sizes': '192x192', 'type': 'image/svg+xml'},
            {'src': '/static/icons/icon-512.svg', 'sizes': '512x512', 'type': 'image/svg+xml'},
        ],
    })
    response['Content-Type'] = 'application/manifest+json'
    return response


@require_http_methods(['GET'])
def service_worker(request):
    response = HttpResponse(SERVICE_WORKER_JS, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response


@require_http_methods(['GET'])
def offline(request):
    return render(request, 'offline.html')


SERVICE_WORKER_JS = """
const CACHE = 'healthwise-static-v2';
const SHELL = ['/offline/'];
self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});
self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(
    keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))
  )));
  self.clients.claim();
});
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request).then((response) => {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        return response;
      }))
    );
    return;
  }
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).catch(() => caches.match('/offline/')));
  }
});
"""

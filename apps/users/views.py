from datetime import date

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.sessions.models import Session
from django.views.decorators.http import require_POST, require_http_methods
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone

from apps.core.models import UserSession
from apps.health import engine
from apps.health.services import award_achievements

from .helpers import qr_data_uri as _qr_data_uri
from .models import UserProfile
from .two_factor import (
    confirm,
    consume_backup_code,
    disable,
    get_settings,
    provisioning_uri,
    start_setup,
    verify_code,
)


def _is_superuser(user):
    return user.is_superuser


# PAGE
@login_required(login_url='login')
@user_passes_test(_is_superuser, login_url='dashboard')
def user_list_page(request):
    query = request.GET.get('q', '').strip()

    users_list = User.objects.all().order_by('-date_joined')

    if query:
        users_list = users_list.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query)
        )

    paginator = Paginator(users_list, 10)
    page_number = request.GET.get('page', 1)
    users = paginator.get_page(page_number)

    return render(request, 'users/list.html', {
        'users': users,
        'query': query,
    })


# LIST USERS (AJAX)
@login_required(login_url='login')
@user_passes_test(_is_superuser, login_url='dashboard')
def user_list_ajax(request):
    users_list = User.objects.all().order_by('-date_joined')
    paginator = Paginator(users_list, 10)
    page_number = request.GET.get('page', 1)
    users = paginator.get_page(page_number)
    data = list(users.object_list.values(
        'id',
        'username',
        'first_name',
        'last_name',
        'email',
        'is_staff',
        'is_active',
        'date_joined',
    ))
    return JsonResponse({
        "data":     data,
        "has_next": users.has_next(),
        "has_prev": users.has_previous(),
        "page":     users.number,
        "pages":    users.paginator.num_pages,
        "total":    users.paginator.count,
    })


# GET SINGLE USER (AJAX)
@login_required(login_url='login')
@user_passes_test(_is_superuser, login_url='dashboard')
def user_get_ajax(request, pk):
    user = get_object_or_404(User, pk=pk)
    return JsonResponse({
        "id":         user.id,
        "username":   user.username,
        "first_name": user.first_name,
        "last_name":  user.last_name,
        "email":      user.email,
        "is_staff":   user.is_staff,
        "is_active":  user.is_active,
    })


# CREATE / UPDATE USER (AJAX)
@login_required(login_url='login')
@user_passes_test(_is_superuser, login_url='dashboard')
@require_POST
def user_save_ajax(request):
    user_id = request.POST.get("id")

    if user_id:
        user = get_object_or_404(User, pk=user_id)
    else:
        user = User()

    username = request.POST.get("username", "").strip()
    email = request.POST.get("email", "").strip()

    if not username:
        return JsonResponse({"error": "Username is required."}, status=400)

    dup_qs = User.objects.filter(Q(username=username) | (Q(email=email) & ~Q(email="")))
    if user_id:
        dup_qs = dup_qs.exclude(pk=user_id)
    if dup_qs.filter(username=username).exists():
        return JsonResponse({"error": "That username is already taken."}, status=400)
    if email and dup_qs.filter(email=email).exists():
        return JsonResponse({"error": "That email is already in use."}, status=400)

    user.username   = username
    user.first_name = request.POST.get("first_name", "")
    user.last_name  = request.POST.get("last_name", "")
    user.email      = email
    user.is_staff   = request.POST.get("is_staff") == "true"
    user.is_active  = request.POST.get("is_active") == "true"

    password = request.POST.get("password")
    if password:
        user.set_password(password)
    elif not user_id:
        return JsonResponse({"error": "Password is required for new users."}, status=400)

    try:
        user.save()
    except IntegrityError:
        return JsonResponse({"error": "Could not save user due to a conflict (duplicate username/email)."}, status=400)

    return JsonResponse({
        "status": "success",
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "is_staff": user.is_staff,
        "is_active": user.is_active,
    })


# DELETE USER (AJAX)
@login_required(login_url='login')
@user_passes_test(_is_superuser, login_url='dashboard')
@require_POST
def user_delete_ajax(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.user == user:
        return JsonResponse({"error": "You cannot delete yourself"}, status=400)
    user.delete()
    return JsonResponse({"status": "deleted"})
# PROFILE
@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    errors = {}
    form = {
        'birthdate': request.POST.get('birthdate', '') if request.method == 'POST' else (
            profile.birthdate.isoformat() if profile.birthdate else ''
        ),
        'sex': request.POST.get('sex', '') if request.method == 'POST' else profile.sex,
        'height_cm': request.POST.get('height_cm', '') if request.method == 'POST' else (
            profile.height_cm or ''
        ),
        'activity_level': request.POST.get('activity_level', '') if request.method == 'POST' else profile.activity_level,
        'family_history': request.POST.get('family_history', '') if request.method == 'POST' else profile.family_history,
        'conditions': request.POST.get('conditions', '') if request.method == 'POST' else profile.conditions,
    }

    if request.method == 'POST':
        birthdate_raw = str(form['birthdate']).strip()
        birthdate_value = None
        if birthdate_raw:
            try:
                birthdate_value = date.fromisoformat(birthdate_raw)
            except ValueError:
                errors['birthdate'] = 'Enter a valid date (YYYY-MM-DD).'
        form['birthdate'] = birthdate_raw

        height_raw = str(form['height_cm']).strip()
        if height_raw:
            try:
                height = int(float(height_raw))
            except ValueError:
                errors['height_cm'] = 'Enter a whole number of centimetres.'
            else:
                if height < 100 or height > 250:
                    errors['height_cm'] = 'Enter a height between 100 and 250 cm.'
                else:
                    form['height_cm'] = height
        else:
            form['height_cm'] = None

        if form['sex'] and form['sex'] not in dict(engine.SEX_CHOICES):
            errors['sex'] = 'Please select a valid option.'
        if form['activity_level'] and form['activity_level'] not in dict(engine.ACTIVITY_LEVELS):
            errors['activity_level'] = 'Please select a valid option.'
        if form['family_history'] not in dict(engine.FAMILY_HISTORY_CHOICES):
            errors['family_history'] = 'Please select a valid option.'
        if form['conditions'] not in dict(engine.CONDITION_CHOICES):
            errors['conditions'] = 'Please select a valid option.'

        if not errors:
            profile.birthdate = birthdate_value
            profile.sex = form['sex']
            profile.height_cm = form['height_cm']
            profile.activity_level = form['activity_level']
            profile.family_history = form['family_history']
            profile.conditions = form['conditions']
            profile.reminder_opt_in = request.POST.get('reminder_opt_in') == 'on'
            profile.phone_number = request.POST.get('phone_number', '').strip()[:30]
            profile.sms_opt_in = request.POST.get('sms_opt_in') == 'on'
            profile.save()
            award_achievements(request.user)
            from apps.core.security import log_event
            log_event(request, 'profile.updated')
            messages.success(request, 'Profile saved. New assessments will be prefilled.')
            return redirect('users:profile')

    return render(request, 'users/profile.html', {
        'profile': profile,
        'form': form,
        'errors': errors,
        'age': profile.age,
        'sex_choices': engine.SEX_CHOICES,
        'activity_choices': engine.ACTIVITY_LEVELS,
        'family_history_choices': engine.FAMILY_HISTORY_CHOICES,
        'condition_choices': engine.CONDITION_CHOICES,
    })


@login_required(login_url='login')
def account_security(request):
    active_keys = Session.objects.filter(
        expire_date__gt=timezone.now(),
    ).values_list('session_key', flat=True)
    sessions = request.user.tracked_sessions.filter(
        ended_at__isnull=True, session_key__in=active_keys,
    )
    return render(request, 'users/security.html', {
        'sessions': sessions,
        'current_session_key': request.session.session_key,
        'two_factor': getattr(request.user, 'two_factor', None),
    })


@login_required(login_url='login')
@require_POST
def end_session(request, pk):
    tracked = get_object_or_404(UserSession, pk=pk, user=request.user)
    is_current = tracked.session_key == request.session.session_key
    Session.objects.filter(session_key=tracked.session_key).delete()
    tracked.ended_at = timezone.now()
    tracked.save(update_fields=['ended_at'])
    if is_current:
        logout(request)
        return redirect('login')
    messages.success(request, 'Session signed out.')
    return redirect('users:security')


@login_required(login_url='login')
@require_http_methods(['GET', 'POST'])
def two_factor_setup(request):
    settings_obj = get_settings(request.user)
    if settings_obj.enabled:
        return render(request, 'users/two_factor.html', {
            'enabled': True,
            'settings_obj': settings_obj,
        })

    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        if verify_code(settings_obj.secret, code):
            confirm(settings_obj)
            messages.success(request, 'Two-factor authentication is now enabled.')
            return render(request, 'users/two_factor.html', {
                'enabled': True,
                'settings_obj': settings_obj,
                'backup_codes': settings_obj.backup_codes,
            })
        messages.error(request, 'That code did not match. Check your authenticator app.')

    if not settings_obj.secret:
        settings_obj = start_setup(request.user)
    uri = provisioning_uri(request.user, settings_obj.secret)
    return render(request, 'users/two_factor.html', {
        'enabled': False,
        'settings_obj': settings_obj,
        'secret': settings_obj.secret,
        'qr': _qr_data_uri(uri),
        'uri': uri,
    })


@login_required(login_url='login')
@require_POST
def two_factor_disable(request):
    settings_obj = get_settings(request.user)
    password = request.POST.get('password', '')
    code = request.POST.get('code', '').strip()
    if not request.user.check_password(password):
        messages.error(request, 'Password is incorrect.')
    elif verify_code(settings_obj.secret, code) or consume_backup_code(settings_obj, code):
        disable(settings_obj)
        messages.success(request, 'Two-factor authentication disabled.')
    else:
        messages.error(request, 'Enter a valid authenticator or backup code.')
    return redirect('users:two_factor_setup')

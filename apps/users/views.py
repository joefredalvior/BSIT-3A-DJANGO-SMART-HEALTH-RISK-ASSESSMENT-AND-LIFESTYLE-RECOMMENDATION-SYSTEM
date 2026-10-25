from datetime import date

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST, require_http_methods
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Avg, Q

from apps.health import engine
from apps.health.models import Assessment

from .models import UserProfile


def _is_superuser(user):
    return user.is_superuser


def _is_clinician(user):
    return user.is_staff or user.is_superuser


# PAGE
@login_required(login_url='core:login')
@user_passes_test(_is_superuser, login_url='core:dashboard')
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
@login_required(login_url='core:login')
@user_passes_test(_is_superuser, login_url='core:dashboard')
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
        'is_superuser',
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
@login_required(login_url='core:login')
@user_passes_test(_is_superuser, login_url='core:dashboard')
def user_get_ajax(request, pk):
    user = get_object_or_404(User, pk=pk)
    return JsonResponse({
        "id":         user.id,
        "username":   user.username,
        "first_name": user.first_name,
        "last_name":  user.last_name,
        "email":      user.email,
        "is_staff":   user.is_staff,
        "is_superuser": user.is_superuser,
        "is_active":  user.is_active,
    })


# CREATE / UPDATE USER (AJAX)
@login_required(login_url='core:login')
@user_passes_test(_is_superuser, login_url='core:dashboard')
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
    user.is_superuser = request.POST.get("is_superuser") == "true"
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
@login_required(login_url='core:login')
@user_passes_test(_is_superuser, login_url='core:dashboard')
@require_POST
def user_delete_ajax(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.user == user:
        return JsonResponse({"error": "You cannot delete yourself"}, status=400)
    user.delete()
    return JsonResponse({"status": "deleted"})
# PROFILE
@login_required(login_url='core:login')
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
            profile.save()
            messages.success(request, 'Profile saved. New assessments will be prefilled.')
            return redirect('users:profile')

    # Profile completeness nudges
    completeness_fields = [
        ('birthdate', 'Date of birth'),
        ('sex', 'Sex'),
        ('height_cm', 'Height'),
        ('activity_level', 'Activity level'),
        ('family_history', 'Family history'),
        ('conditions', 'Existing conditions'),
    ]
    missing = [label for field, label in completeness_fields if not getattr(profile, field, None)]
    completeness_pct = int(round((1 - len(missing) / len(completeness_fields)) * 100))

    return render(request, 'users/profile.html', {
        'profile': profile,
        'form': form,
        'errors': errors,
        'age': profile.age,
        'sex_choices': engine.SEX_CHOICES,
        'activity_choices': engine.ACTIVITY_LEVELS,
        'family_history_choices': engine.FAMILY_HISTORY_CHOICES,
        'condition_choices': engine.CONDITION_CHOICES,
        'completeness_pct': completeness_pct,
        'completeness_missing': missing,
    })


# CLINICIAN DASHBOARD
@login_required(login_url='core:login')
@user_passes_test(_is_clinician, login_url='core:dashboard')
def clinician_dashboard(request):
    """
    Display the clinician dashboard with risk assessment statistics.
    
    Context variables passed to template:
        - assessments: Paginated list of all assessments (filtered by search query)
        - query: Search query string from request GET parameters
        - total: Total count of assessments
        - average_score: Average risk score across all assessments (or None)
        - high_risk_count: Count of assessments with High or Critical risk level
        - total_patients: Count of distinct patients who have assessments
        - today_assessments: Count of assessments created today
        - risk_distribution: QuerySet with risk level breakdown (risk_level + count)
        - active_patients: Count of patients assessed in the last 30 days
    """
    query = request.GET.get('q', '').strip()
    assessments = Assessment.objects.select_related('user').all()

    if query:
        assessments = assessments.filter(
            Q(user__username__icontains=query) |
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query)
        )

    stats = assessments.aggregate(average=Avg('risk_score'))
    high_risk_count = assessments.filter(risk_level__in=['High', 'Critical']).count()

    # Additional statistics
    total_patients = assessments.values('user').distinct().count()
    today_assessments = assessments.filter(
        created_at=datetime.now().date()
    ).count()

    # Risk distribution
    risk_distribution = assessments.values('risk_level').annotate(
        count=Count('id')
    ).order_by('risk_level')

    # Active patients (last 30 days)
    from datetime import timedelta
    thirty_days_ago = datetime.now() - timedelta(days=30)
    active_patients = assessments.filter(
        created_at__gte=thirty_days_ago
    ).values('user').distinct().count()

    paginator = Paginator(assessments, 20)
    page = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'users/clinician.html', {
        'assessments': page,
        'query': query,
        'total': assessments.count(),
        'average_score': int(round(stats['average'])) if stats['average'] is not None else None,
        'high_risk_count': high_risk_count,
        'total_patients': total_patients,
        'today_assessments': today_assessments,
        'risk_distribution': risk_distribution,
        'active_patients': active_patients,
    })


# PASSWORD CHANGE
@login_required(login_url='core:login')
@require_http_methods(['GET', 'POST'])
def password_change(request):
    """Let the signed-in user change their own password."""
    if request.method == 'POST':
        old_password = request.POST.get('old_password', '')
        new_password1 = request.POST.get('new_password1', '')
        new_password2 = request.POST.get('new_password2', '')

        if not request.user.check_password(old_password):
            messages.error(request, 'Your current password is incorrect.')
        elif new_password1 != new_password2:
            messages.error(request, 'The two new passwords do not match.')
        elif len(new_password1) < 8:
            messages.error(request, 'Password must be at least 8 characters.')
        elif new_password1 == old_password:
            messages.error(request, 'New password must differ from your current password.')
        else:
            request.user.set_password(new_password1)
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Your password was changed successfully.')
            return redirect('users:profile')

    return render(request, 'users/password_change.html')


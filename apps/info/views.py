from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError
from django.db.models import Q

from apps.health import engine
from apps.scoping import scoped_info, scoped_infos
from .models import Info

MIN_AGE = 1
MAX_AGE = 150


def _parse_age(raw_age):
    try:
        return int(raw_age)
    except (TypeError, ValueError):
        return None


@login_required(login_url='login')
def info_list_page(request):
    query = request.GET.get('q', '').strip()

    infos_list = scoped_infos(request.user).order_by('name')

    if query:
        infos_list = infos_list.filter(
            Q(name__icontains=query) |
            Q(address__icontains=query) |
            Q(email__icontains=query)
        )

    paginator = Paginator(infos_list, 10)
    page_number = request.GET.get('page', 1)
    infos = paginator.get_page(page_number)

    return render(request, 'info.html', {
        'infos': infos,
        'query': query,
    })


@login_required(login_url='login')
def info_list_ajax(request):
    query = request.GET.get('q', '').strip()

    infos_list = scoped_infos(request.user).order_by('name')

    if query:
        infos_list = infos_list.filter(
            Q(name__icontains=query) |
            Q(address__icontains=query) |
            Q(email__icontains=query)
        )

    paginator = Paginator(infos_list, 10)
    page_number = request.GET.get('page', 1)
    infos = paginator.get_page(page_number)
    data = list(infos.object_list.values('id', 'name', 'age', 'address', 'email'))
    return JsonResponse({
        'data': data,
        'has_next': infos.has_next(),
        'has_prev': infos.has_previous(),
        'page': infos.number,
        'pages': infos.paginator.num_pages,
        'total': infos.paginator.count,
    })


@login_required(login_url='login')
def info_get_ajax(request, pk):
    info = scoped_info(request.user, pk)
    return JsonResponse({
        'id': info.id,
        'name': info.name,
        'age': info.age,
        'address': info.address,
        'email': info.email,
    })


@login_required(login_url='login')
@require_POST
def info_save_ajax(request):
    info_id = request.POST.get('id')

    if info_id:
        info = scoped_info(request.user, info_id)
    else:
        info = Info()

    name = request.POST.get('name', '').strip()
    age = request.POST.get('age', '').strip()
    address = request.POST.get('address', '').strip()
    email = request.POST.get('email', '').strip()

    if not name:
        return JsonResponse({'error': 'Name is required.'}, status=400)

    if not age:
        return JsonResponse({'error': 'Age is required.'}, status=400)

    age_value = _parse_age(age)

    if age_value is None or age_value < MIN_AGE or age_value > MAX_AGE:
        return JsonResponse(
            {'error': f'Age must be a number between {MIN_AGE} and {MAX_AGE}.'},
            status=400
        )

    if not address:
        return JsonResponse({'error': 'Address is required.'}, status=400)

    if email:
        try:
            validate_email(email)
        except ValidationError:
            return JsonResponse({'error': 'Enter a valid email address.'}, status=400)

    info.name = name
    info.age = age_value
    info.address = address
    info.email = email

    if not info.pk:
        info.user = request.user

    try:
        info.save()
    except IntegrityError:
        return JsonResponse(
            {'error': 'Could not save record due to a conflict.'},
            status=400
        )

    return JsonResponse({
        'status': 'success',
        'id': info.id,
        'name': info.name,
        'age': info.age,
        'address': info.address,
        'email': info.email,
    })


@login_required(login_url='login')
@require_POST
def info_delete_ajax(request, pk):
    info = scoped_info(request.user, pk)
    info.delete()
    return JsonResponse({'status': 'deleted'})

GUIDE_SECTIONS = [
    {
        'title': 'Body mass index (BMI)',
        'summary': 'A ratio of weight to height used to screen for underweight, overweight and obesity.',
        'bands': [
            ('Below 18.5', 'Underweight'),
            ('18.5 - 24.9', 'Healthy weight'),
            ('25.0 - 29.9', 'Overweight'),
            ('30.0 - 34.9', 'Obesity class I'),
            ('35.0 - 39.9', 'Obesity class II'),
            ('40.0 and above', 'Obesity class III'),
        ],
    },
    {
        'title': 'Blood pressure',
        'summary': 'Systolic (top) and diastolic (bottom) pressure in millimetres of mercury (mmHg).',
        'bands': [
            ('Below 120/80', 'Normal'),
            ('120-129 / below 80', 'Elevated'),
            ('130-139 / 80-89', 'Stage 1 hypertension'),
            ('140+ / 90+', 'Stage 2 hypertension'),
            ('180+ / 120+', 'Hypertensive crisis - seek urgent care'),
        ],
    },
    {
        'title': 'Waist and waist-to-height ratio',
        'summary': 'Central fat is closely linked to heart disease and type 2 diabetes.',
        'bands': [
            ('Waist below 94 cm (men)', 'Lower risk'),
            ('Waist below 80 cm (women)', 'Lower risk'),
            ('Waist-to-height below 0.5', 'Healthy'),
            ('Waist-to-height 0.5 - 0.59', 'Increased risk'),
            ('Waist-to-height 0.6+', 'High risk'),
        ],
    },
    {
        'title': 'Physical activity',
        'summary': 'Adults should aim for at least 150 minutes of moderate activity each week.',
        'bands': [
            ('Sedentary', 'Little or no exercise'),
            ('Light', '1-3 days per week'),
            ('Moderate', '3-5 days per week'),
            ('Active', '6-7 days per week'),
        ],
    },
    {
        'title': 'Sleep',
        'summary': 'Most adults need 7-9 hours of sleep per night for recovery and metabolic health.',
        'bands': [
            ('Under 6 hours', 'Short sleep'),
            ('7-9 hours', 'Recommended range'),
            ('Over 9 hours', 'Long sleep'),
        ],
    },
    {
        'title': 'Smoking, alcohol and stress',
        'summary': 'These lifestyle factors interact with blood pressure, sleep and weight.',
        'bands': [
            ('Smoking', 'Any amount raises cardiovascular risk; quitting is the biggest single gain'),
            ('Alcohol', 'Keep to no more than 14 units per week, spread across days'),
            ('Stress', 'Chronic stress affects blood pressure, sleep and eating patterns'),
        ],
    },
]


@login_required(login_url='login')
def guide(request):
    """Static educational reference for every factor the engine scores."""
    return render(request, 'info/guide.html', {
        'sections': GUIDE_SECTIONS,
        'disclaimer': engine.MEDICAL_DISCLAIMER,
    })

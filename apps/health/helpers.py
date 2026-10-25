"""Pure and queryset helpers used by health views."""

from django.core.cache import cache
from django.db.models import Max

from apps.users.models import UserProfile

from . import engine
from .models import Assessment

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
GOAL_METRICS_HIGHER_IS_BETTER = {'sleep_hours', 'fruit_veg_servings'}


def is_clinician(user):
    return user.is_staff or user.is_superuser


def initial_form(user):
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
    return {
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


def serialize_findings(result):
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


def compare(previous, current):
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


def trend_payload(user, upto=None, limit=12):
    latest_id = Assessment.objects.filter(user=user).aggregate(max_id=Max('pk'))['max_id']
    cache_key = f'trend:{user.pk}:{latest_id}:{upto.isoformat() if upto else "latest"}:{limit}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    queryset = Assessment.objects.filter(user=user).order_by('created_at')
    if upto is not None:
        queryset = queryset.filter(created_at__lte=upto)
    records = list(queryset)[-limit:]
    payload = [
        {
            'date': record.created_at.strftime('%d %b %y'),
            'score': record.risk_score,
            'bmi': float(record.bmi) if record.bmi is not None else None,
            'systolic': record.systolic,
            'diastolic': record.diastolic,
        }
        for record in records
    ]
    cache.set(cache_key, payload, timeout=60)
    return payload


def goal_progress(goal, latest):
    current = None
    if latest is not None:
        current = getattr(latest, goal.metric, None)
    target = float(goal.target_value)
    if current is None:
        return {'current': None, 'target': target, 'percent': 0, 'met': False}
    current_value = float(current)
    higher_is_better = goal.metric in GOAL_METRICS_HIGHER_IS_BETTER
    met = current_value >= target if higher_is_better else current_value <= target
    if higher_is_better:
        percent = 100 if target <= 0 else (current_value / target) * 100
    else:
        percent = 100 if current_value <= 0 else (target / current_value) * 100
    return {
        'current': round(current_value, 1),
        'target': target,
        'percent': max(0, min(round(percent), 100)),
        'met': met,
    }

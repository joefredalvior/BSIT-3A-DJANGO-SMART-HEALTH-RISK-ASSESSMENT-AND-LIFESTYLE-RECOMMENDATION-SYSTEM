"""Wellness view helpers."""

from django.utils import timezone


def is_clinician(user):
    return user.is_staff or user.is_superuser


def vitals_payload(user):
    rows = []
    for reading in user.vital_readings.all()[:60]:
        rows.append({
            'date': timezone.localtime(reading.measured_at).strftime('%d %b %y'),
            'weight': float(reading.weight_kg) if reading.weight_kg is not None else None,
            'bmi': reading.bmi,
            'systolic': reading.systolic,
            'diastolic': reading.diastolic,
            'sleep': float(reading.sleep_hours) if reading.sleep_hours is not None else None,
            'exercise': reading.exercise_minutes,
        })
    return list(reversed(rows))

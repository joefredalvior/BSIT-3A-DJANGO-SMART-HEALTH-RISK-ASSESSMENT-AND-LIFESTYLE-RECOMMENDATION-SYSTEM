from django.urls import path

from . import views

app_name = 'wellness'

urlpatterns = [
    path('vitals/', views.vitals, name='vitals'),
    path('vitals/import/', views.import_vitals, name='import_vitals'),
    path('vitals/<int:pk>/delete/', views.delete_vital, name='delete_vital'),

    path('appointments/', views.appointments, name='appointments'),
    path('appointments/<int:pk>/cancel/', views.cancel_appointment, name='cancel_appointment'),
    path('clinician/appointments/', views.clinician_appointments, name='clinician_appointments'),

    path('messages/', views.inbox, name='inbox'),
    path('messages/new/', views.compose_message, name='compose_message'),
    path('messages/<int:pk>/', views.message_detail, name='message_detail'),
    path('messages/<int:pk>/reply/', views.reply_message, name='reply_message'),

    path('screenings/', views.screenings, name='screenings'),
    path('screenings/<int:pk>/', views.screening_detail, name='screening_detail'),

    path('medications/', views.medications, name='medications'),
    path('medications/<int:pk>/toggle/', views.toggle_medication, name='toggle_medication'),
    path('medications/<int:pk>/delete/', views.delete_medication, name='delete_medication'),

    path('clinics/', views.clinics, name='clinics'),

    path('feedback/<int:pk>/', views.submit_feedback, name='submit_feedback'),

    path('caregivers/', views.caregivers, name='caregivers'),
    path('caregivers/dashboard/', views.caregiver_dashboard, name='caregiver_dashboard'),
    path('caregivers/accept/<str:token>/', views.caregiver_accept, name='caregiver_accept'),
    path('caregivers/<int:pk>/revoke/', views.caregiver_revoke, name='caregiver_revoke'),
    path(
        'caregivers/<int:pk>/report/<int:assessment_pk>/',
        views.caregiver_report,
        name='caregiver_report',
    ),

    path('achievements/', views.achievements, name='achievements'),
]

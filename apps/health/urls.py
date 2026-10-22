from django.urls import path

from . import views

app_name = 'health'

urlpatterns = [
    path('', views.assessment_form, name='assessment_form'),
    path('history/', views.history, name='history'),
    path('report/<int:pk>/', views.report, name='report'),
    path('report/<int:pk>/export/', views.export, name='export'),
    path('report/<int:pk>/delete/', views.delete_assessment, name='delete'),
    path('clinician/report/<int:pk>/', views.clinician_report, name='clinician_report'),
]
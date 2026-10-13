from django.urls import path

from . import views

app_name = 'health'

urlpatterns = [
    path('', views.assessment_form, name='assessment_form'),
    path('history/', views.history, name='history'),
    path('report/<int:pk>/', views.report, name='report'),
]
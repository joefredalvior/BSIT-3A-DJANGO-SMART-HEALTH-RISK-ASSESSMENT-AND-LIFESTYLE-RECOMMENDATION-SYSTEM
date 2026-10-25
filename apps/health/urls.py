from django.urls import path

from . import views

app_name = 'health'

urlpatterns = [
    path('', views.assessment_form, name='assessment_form'),
    path('history/', views.history, name='history'),
    path('goals/', views.goals, name='goals'),
    path('goals/<int:pk>/delete/', views.delete_goal, name='goal_delete'),
    path('report/<int:pk>/', views.report, name='report'),
    path('report/<int:pk>/export/', views.export, name='export'),
    path('report/<int:pk>/email/', views.email_report, name='email_report'),
    path('report/<int:pk>/pdf/', views.report_pdf, name='report_pdf'),
    path('report/<int:pk>/share/', views.share_report, name='share_report'),
    path('share/<int:pk>/revoke/', views.revoke_share, name='revoke_share'),
    path('shared/<str:token>/', views.shared_report, name='shared_report'),
    path('report/<int:pk>/delete/', views.delete_assessment, name='delete'),
    path('simulate/', views.simulate, name='simulate'),
    path('clinician/report/<int:pk>/', views.clinician_report, name='clinician_report'),
    path('clinician/report/<int:pk>/note/', views.add_clinician_note, name='add_note'),
    path('api/assessments/', views.api_assessments, name='api_assessments'),
    path('api/assessments/<int:pk>/', views.api_assessment_detail, name='api_detail'),
]
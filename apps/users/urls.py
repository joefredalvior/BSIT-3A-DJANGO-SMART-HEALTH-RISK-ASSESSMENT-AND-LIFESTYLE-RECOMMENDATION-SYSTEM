from django.urls import path
from . import views
from apps.health.views import clinician_dashboard

app_name = 'users'

urlpatterns = [
    # Page
    path('', views.user_list_page, name='user_list'),
    path('profile/', views.profile_view, name='profile'),
    path('security/', views.account_security, name='security'),
    path('security/sessions/<int:pk>/end/', views.end_session, name='end_session'),
    path('security/2fa/', views.two_factor_setup, name='two_factor_setup'),
    path('security/2fa/disable/', views.two_factor_disable, name='two_factor_disable'),
    path('clinician/', clinician_dashboard, name='clinician'),
    # AJAX
    path('ajax/list/', views.user_list_ajax, name='user_list_ajax'),
    path('ajax/get/<int:pk>/', views.user_get_ajax, name='user_get_ajax'),
    path('ajax/save/', views.user_save_ajax, name='user_save_ajax'),
    path('ajax/delete/<int:pk>/', views.user_delete_ajax, name='user_delete_ajax'),
]
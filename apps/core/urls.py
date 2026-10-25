from django.urls import path

from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('home/', views.home, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('privacy/', views.privacy_policy, name='privacy'),
    path('healthz/', views.healthz, name='healthz'),
    path('language/<str:lang>/', views.set_language, name='set_language'),
    path('two-factor/challenge/', views.two_factor_challenge, name='two_factor_challenge'),

    path('audit/', views.audit_log, name='audit_log'),
    path('audit/export/', views.audit_log_export, name='audit_log_export'),

    path('manifest.webmanifest', views.manifest, name='manifest'),
    path('sw.js', views.service_worker, name='service_worker'),
    path('offline/', views.offline, name='offline'),

    path('verify-email/<str:token>/', views.verify_email, name='verify_email'),
    path('verify-email/resend/', views.resend_verification, name='resend_verification'),

    path('password-reset/', views.HealthWisePasswordResetView.as_view(), name='password_reset'),
    path('password-reset/done/', views.HealthWisePasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', views.HealthWisePasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', views.HealthWisePasswordResetCompleteView.as_view(), name='password_reset_complete'),
    path('password-change/', views.HealthWisePasswordChangeView.as_view(), name='password_change'),

    path('account/export/', views.account_export, name='account_export'),
    path('account/delete/', views.account_delete, name='account_delete'),
]

from django.urls import path
from . import views
from .api_views import *
from .views import *

app_name = 'patients'

urlpatterns = [

    path('', landing, name='landing'),

    # Template-based views
    path('patients/register/', views.register, name='register'),
    path('patients/login/', views.login_view, name='login'),
    path('patients/logout/', views.logout_view, name='logout'),
    path('contact/', views.contact, name='contact'),
    path('home/', views.home, name='home'),
    path('profile/', views.profile, name='profile'),
    path('profile/update/', views.update_profile, name='update_profile'),

    path('message/<int:message_id>/', views.view_message, name='view_message'),
    path('medication-reminders/', views.medication_reminders, name='medication_reminders'),
    # path('bill-list/', views.bill_list, name='bill_list'),
    path('treatment-plans/', views.treatment_plans, name='treatment_plans'),  # New Treatment Plans URL
    path('emergency-contact/', views.emergency_contact, name='emergency_contact'),  # New Emergency Contact URL
    path('feedback/', views.feedback_form, name='feedback_form'),

    # Patient messages
    path('patient/messages/', views.patient_messages, name='patient_messages'),

    path('reports/', views.report_list, name='report_list'),
    path('report/<int:report_id>/', views.report_detail, name='report_detail'),
    path('report/download/<int:report_id>/', views.download_report, name='download_report'),

    # API views
    path('api/landing/', api_landing, name='api_landing'),
    path('api/register/', api_register, name='api_register'),
    path('api/login/', api_login, name='api_login'),
    path('api/logout/', api_logout, name='api_logout'),
    path('api/profile/', api_profile, name='api_profile'),
    path('api/profile/update/', api_update_profile, name='api_update_profile'),
    path('api/medication-reminders/', api_medication_reminders, name='api_medication_reminders'),
    path('api/feedback/', api_feedback, name='api_feedback'),
    path('api/treatment-plans/', api_treatment_plans, name='api_treatment_plans'),
    path('api/emergency-contact/', api_emergency_contact, name='api_emergency_contact'),
]

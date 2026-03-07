from django.urls import path, include
from . import views
from rest_framework.routers import DefaultRouter
from .api_views import *
from .views import *
from django.urls import resolve


app_name = 'staff'

router = DefaultRouter()

router.register(r'staffs', StaffViewSet, basename='staff-users')
router.register(r'doctors', DoctorViewSet, basename='doctor')
router.register(r'doctor-schedules', DoctorScheduleViewSet, basename='doctor_schedule')
router.register(r'appointments', AppointmentViewSet, basename='appointment')
router.register(r'patient-vitals', VitalSignViewSet, basename='patient_vital')
router.register(r'care-plans', CarePlanViewSet, basename='care_plan')
router.register(r'medical-records', MedicalRecordViewSet, basename='medical_record')
router.register(r'lab-test-results', LabTestViewSet, basename='lab_test_result')
router.register(r'prescriptions', PrescriptionViewSet, basename='prescription')
router.register(r'insurances', InsuranceViewSet, basename='insurance')
router.register(r'bills', BillViewSet, basename='bill')
router.register(r'insurance-claims', InsuranceClaimViewSet, basename='insurance_claim')
router.register(r'supplies', MedicalSupplyViewSet, basename='medical_supply')
router.register(r'alerts', StockAlertViewSet, basename='stock_alert')
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'performance-metrics', HospitalPerformanceMetricsViewSet, basename='performance_metrics')
router.register(r'resource-allocations', ResourceAllocationViewSet, basename='resource_allocation')
router.register(r'performance-analytics', PerformanceAnalyticsViewSet, basename='performance_analytics')
router.register(r'reports', ReportViewSet, basename='report')
router.register(r'audit-logs', AuditLogViewSet, basename='audit-log')
router.register(r'health-and-safety-protocols', HealthAndSafetyProtocolViewSet, basename='health-and-safety-protocol')
router.register(r'infection-control-practices', InfectionControlPracticeViewSet, basename='infection-control-practice')
router.register(r'certifications', CertificationViewSet, basename='certification')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'patients', PatientViewSet, basename='patient')
router.register(r'doctor-patient-messages/(?P<patient_id>\d+)/', DoctorPatientMessageList, basename='doctor-patient-messages')

custom_auth_urls = [
    path('login/', LoginView.as_view(), name='staff-login'),
    path('register/', RegisterView.as_view(), name='staff-register'),
    path('logout/', staff_logout, name='staff-logout'),  # Use standalone logout view
    path('test/', TestView.as_view(), name='test_view'),
    path('api_staff_dashboard/', StaffDashboardView.as_view(), name='api_staff_dashboard'),
]

urlpatterns = [
    # Register and login URLs
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard
    path('dashboard/', views.staff_dashboard, name='dashboard'),

    path('search/', views.search_patient, name='search_patient'),
    path('patient/<int:patient_id>/', views.display_patient, name='display_patient'),
    path('patient/<int:patient_id>/appointments/', views.view_patient_appointments, name='view_patient_appointments'),
path('patient/<int:patient_id>/records/', views.staff_patient_records, name='staff_patient_records'),
    # Doctor-specific views
    path('doctor/', views.doctor_view, name='doctor_view'),
    path('doctor/schedule/', views.doctor_schedule, name='doctor_schedule'),

    # Appointment management
    path('assign_appointment/<int:patient_id>/', views.assign_appointment, name='assign_appointment'),
    path('appointment/<int:appointment_id>/', views.view_appointment, name='view_appointment'),
    path('appointment/<int:appointment_id>/add_note/', views.add_consultation_note, name='add_consultation_note'),

    # Patient assignments
    path('patient/assignments/', views.patient_assignments, name='patient_assignments'),
    path('patient/assignments/<int:assignment_id>/manage/', views.manage_patient_assignment,
         name='manage_patient_assignment'),

    # Vital signs management
    path('patient/<int:patient_id>/add_vitals/', views.add_vitals, name='add_vitals'),
    path('patient/<int:patient_id>/view_vitals/', views.view_vitals, name='view_vitals'),

    # Progress tracking
    path('patient/<int:patient_id>/add_progress_tracking/', views.add_progress_tracking, name='add_progress_tracking'),
    path('patient/<int:patient_id>/view_progress_tracking/', views.view_progress_tracking,
         name='view_progress_tracking'),

    # Care plan management
    path('patient/<int:patient_id>/add_care_plan/', views.add_care_plan, name='add_care_plan'),
    path('patient/<int:patient_id>/view_care_plan/', views.view_care_plan, name='view_care_plan'),

    # Medical record management
    path('patient/<int:patient_id>/add_medical_record/', views.add_medical_record, name='add_medical_record'),
    path('patient/<int:patient_id>/view_medical_record/', views.view_medical_record, name='view_medical_record'),

    # Lab tests management
    path('patient/<int:patient_id>/order_lab_test/', views.order_lab_test, name='order_lab_test'),
    path('patient/<int:patient_id>/view_lab_tests/', views.view_lab_tests, name='view_lab_tests'),
    path('lab_test/<int:lab_test_id>/add_result/', views.add_lab_result, name='add_lab_result'),

    # Prescriptions management
    path('patient/<int:patient_id>/prescribe_medication/', views.prescribe_medication, name='prescribe_medication'),
    path('patient/<int:patient_id>/view_prescriptions/', views.view_prescriptions, name='view_prescriptions'),

    # Staff messages
    path('staff/messages/', views.staff_messages, name='staff_messages'),
    path('staff/messages/send/', views.send_staff_message, name='send_staff_message'),
    path('inbox/', views.staff_inbox, name='staff_inbox'),
    path('message/<int:message_id>/', views.message_detail, name='message_detail'),

    # Doctor-patient messages
    path('doctor/patient/<int:patient_id>/messages/', views.doctor_patient_messages, name='doctor_patient_messages'),

    # Team collaboration
    path('team/collaboration/<int:patient_id>/', views.team_collaboration, name='team_collaboration'),

    path('verify-insurance/<int:patient_id>/', insurance_verification, name='insurance_verification'),
    path('verify-insurance/<int:insurance_id>/verify/', verify_insurance, name='verify_insurance'),
    path('patient/<int:patient_id>/bill_tracking/', views.bill_creation_and_tracking, name='bill_tracking'),
    path('bill/<int:bill_id>/insurance_claim_submission/', views.insurance_claim_submission,
         name='insurance_claim_submission'),

    path('emergency_alerts/', views.emergency_alert_list, name='emergency_alert_list'),
    path('emergency_alerts/acknowledge/<int:pk>/', views.acknowledge_alert, name='acknowledge_alert'),
    path('emergency_alerts/resolve/<int:pk>/', views.resolve_alert, name='resolve_alert'),

    path('inventory/', views.medical_supply_inventory, name='medical_supply_inventory'),
    path('alerts/', views.stock_alerts, name='stock_alerts'),
    path('orders/', views.order_management, name='order_management'),

    path('dashboard/', dashboard_view, name='dashboard'),

    path('resource-allocation/', resource_allocation_view, name='resource_allocation'),

    path('reports/<int:patient_id>/', views.report_list, name='report_list'),
    path('report/<int:report_id>/', views.report_detail, name='report_detail'),
    path('report/create/<int:patient_id>/', views.create_report, name='create_report'),
    path('report/download/<int:report_id>/', views.download_report, name='download_report'),


    path('audit-logs/', audit_log_list, name='audit_log_list'),
    path('audit-logs/<int:log_id>/', audit_log_detail, name='audit_log_detail'),

    path('health-and-safety-protocols/', views.health_and_safety_protocols, name='health_and_safety_protocols'),
    path('infection-control-practices/', views.infection_control_practices, name='infection_control_practices'),

    path('staff/', views.staff_list, name='staff_list'),  # URL for listing all staff members
    path('staff/<int:staff_id>/certifications/', views.staff_certifications, name='staff_certifications'),
    # URL for showing certifications for a specific staff member


    path('emergency-alerts/', EmergencyAlertCreateView.as_view, name='emergency-alert-create'),
    path('emergency-alerts/', EmergencyAlertListView.as_view(), name='emergency_alert_list'),
    path('emergency-alerts/update/<int:pk>/', EmergencyAlertUpdateView.as_view(), name='emergency_alert_update'),

    path('unauthorized/', views.unauthorized, name='unauthorized'),


    # API Routes for Doctor, Appointment, etc.
    path('api/', include(router.urls)),
    path('api/auth/', include(custom_auth_urls)),
]
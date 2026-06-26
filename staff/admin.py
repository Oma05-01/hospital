from django.contrib import admin
from .models import *
from django.contrib.auth.admin import UserAdmin

# --- NEW INLINE CONFIGURATION FOR SCHEDULING ---

class TimeBlockInline(admin.TabularInline):
    model = TimeBlock
    extra = 1  # Provides one blank row by default for easy data entry
    # Optional: order by day so the UI looks clean
    ordering = ['day_of_week', 'start_time']

@admin.register(DoctorSchedule)
class DoctorScheduleAdmin(admin.ModelAdmin):
    list_display = ['doctor', 'appointment_duration', 'buffer_time']
    inlines = [TimeBlockInline] # This is the magic that puts them on the same page

# --- STANDARD REGISTRATIONS ---

admin.site.register(Staff)
# admin.site.register(DoctorSchedule) <-- DELETE THIS OLD LINE!
admin.site.register(Appointment)
admin.site.register(ConsultationNote)
admin.site.register(Assignment)
admin.site.register(VitalSign)
admin.site.register(ProgressTracking)
admin.site.register(CarePlan)
admin.site.register(MedicalRecord)
admin.site.register(LabTest)
admin.site.register(LabResult)
admin.site.register(Prescription)
admin.site.register(StaffMessage)
admin.site.register(DoctorPatientMessage)
admin.site.register(TeamMessage)
admin.site.register(Insurance)
admin.site.register(Bill)
admin.site.register(InsuranceClaim)
admin.site.register(EmergencyAlert)
admin.site.register(MedicalSupply)
admin.site.register(StockAlert)
admin.site.register(Order)
admin.site.register(HospitalPerformanceMetrics)
admin.site.register(ResourceAllocation)
admin.site.register(PerformanceAnalytics)
admin.site.register(Report)
admin.site.register(AuditLog)
admin.site.register(HealthAndSafetyProtocol)
admin.site.register(InfectionControlPractice)
admin.site.register(Certification)
admin.site.register(Notification)
admin.site.register(TokenLog)
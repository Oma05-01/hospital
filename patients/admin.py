from django.contrib import admin
from .models import *

# Register your models here.
admin.site.register(PatientProfile)
admin.site.register(MedicationReminder)
admin.site.register(TreatmentPlan)
# admin.site.register(Bill)
admin.site.register(Feedback)
admin.site.register(EmergencyService)
admin.site.register(TokenLog)
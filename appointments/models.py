from django.db import models
# Updated import to match our optimized schema from earlier
from patients.models import PatientProfile
from staff.models import Appointment


class ConsultationNote(models.Model):
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='consultation_note')
    notes = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # Good to know when notes are amended

    def __str__(self):
        # BUG FIX: You need to chain through `.user.username` to get the patient's username
        return f"Notes for {self.appointment.patient.user.username} - {self.appointment.consultation_type}"
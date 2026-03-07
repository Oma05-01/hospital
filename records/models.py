from django.db import models
from patients.models import PatientProfile
from staff.models import Staff  # We need this to link the doctor!


class MedicalRecord(models.Model):
    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name='medical_records')
    # CRITICAL ADDITION: Track which doctor created this record
    doctor = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, related_name='authored_records')

    diagnosis = models.TextField()
    treatment = models.TextField()
    date_recorded = models.DateField(auto_now_add=True)

    def __str__(self):
        # Safely access the username through the User relationship
        return f"Record for {self.patient.user.username} on {self.date_recorded}"


class HealthReport(models.Model):
    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name='health_reports')
    # Track who uploaded the lab result/report (e.g., a lab technician or doctor)
    uploaded_by = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True)

    report_name = models.CharField(max_length=100)
    report_file = models.FileField(upload_to='health_reports/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.report_name} - {self.patient.user.username}"


class Prescription(models.Model):
    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name='prescriptions')
    # CRITICAL ADDITION: Prescriptions are legally invalid without an issuing doctor
    prescribing_doctor = models.ForeignKey(Staff, on_delete=models.RESTRICT, related_name='issued_prescriptions', blank=True, null=True)

    prescription_details = models.TextField()
    issued_at = models.DateField(auto_now_add=True)
    expires_at = models.DateField()

    def __str__(self):
        return f"Prescription for {self.patient.user.username} (Expires: {self.expires_at})"
from django import forms
from django.core.exceptions import ValidationError
from datetime import date
from .models import MedicalRecord, HealthReport, Prescription

class MedicalRecordForm(forms.ModelForm):
    class Meta:
        model = MedicalRecord
        fields = ['diagnosis', 'treatment']
        widgets = {
            'diagnosis': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter clinical diagnosis...',
                'rows': 4
            }),
            'treatment': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Outline the treatment plan...',
                'rows': 4
            }),
        }

class HealthReportForm(forms.ModelForm):
    class Meta:
        model = HealthReport
        fields = ['report_name', 'report_file']
        widgets = {
            'report_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Blood Panel - Feb 2026'
            }),
            'report_file': forms.FileInput(attrs={'class': 'form-control'}),
        }

class PrescriptionForm(forms.ModelForm):
    class Meta:
        model = Prescription
        fields = ['prescription_details', 'expires_at']
        widgets = {
            'prescription_details': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Medication name, dosage, and frequency...',
                'rows': 3
            }),
            'expires_at': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
        }

    def clean_expires_at(self):
        expiry_date = self.cleaned_data.get('expires_at')
        if expiry_date and expiry_date < date.today():
            raise ValidationError("The prescription expiry date cannot be in the past.")
        return expiry_date
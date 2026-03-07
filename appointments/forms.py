from datetime import date
from django import forms
from django.core.exceptions import ValidationError

# CRITICAL FIX: Import the consolidated models directly from the staff app
from staff.models import Appointment, Staff

class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ['doctor', 'date', 'time', 'reason']
        widgets = {
            # HTML5 native date/time pickers for superior mobile UX
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'doctor': forms.Select(attrs={'class': 'form-control'}),
            'reason': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'placeholder': 'Briefly describe your reason for visit...'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.patient = kwargs.pop('patient', None)
        super().__init__(*args, **kwargs)

        if self.patient:
            # Filter by the assigned patient using the reverse relation
            # Note: Ensure 'doctor_assignments' matches the related_name on your Assignment model!
            assigned_doctors = Staff.objects.filter(
                role__iexact='doctor',
                doctor_assignments__patient=self.patient
            ).distinct()

            # Fallback logic: If the patient is new and has no assigned doctors yet,
            # allow them to choose from the general pool of all doctors.
            if assigned_doctors.exists():
                self.fields['doctor'].queryset = assigned_doctors
            else:
                self.fields['doctor'].queryset = Staff.objects.filter(role__iexact='doctor')

    def clean_date(self):
        """
        Validation: Prevent the patient from booking an appointment in the past.
        """
        appointment_date = self.cleaned_data.get('date')
        if appointment_date and appointment_date < date.today():
            raise ValidationError("You cannot book an appointment in the past.")
        return appointment_date


class RescheduleAppointmentForm(forms.Form):
    new_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    new_time = forms.TimeField(
        widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'})
    )

    def clean_new_date(self):
        """
        Validation: Prevent the patient from rescheduling to a past date.
        """
        new_date = self.cleaned_data.get('new_date')
        if new_date and new_date < date.today():
            raise ValidationError("You cannot reschedule to a date in the past.")
        return new_date
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from datetime import datetime, date
from patients.models import PatientProfile
from .forms import *
from django.contrib import messages
from staff.models import Staff, Appointment, ConsultationNote

now = datetime.now()
today = now.date()


@login_required
def book_appointment(request):
    # Security: Ensure only patients can book
    if not hasattr(request.user, 'patient_profile'):
        messages.error(request, "Only registered patients can access this portal.")
        return redirect('home')

    patient_profile = request.user.patient_profile

    if request.method == 'POST':
        form = AppointmentForm(request.POST, patient=patient_profile)
        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.patient = patient_profile
            appointment.save()
            messages.success(request, "Your appointment has been successfully booked.")
            return redirect('appointments:appointment_list')
    else:
        form = AppointmentForm(patient=patient_profile)

    return render(request, 'appointments/book_appointment.html', {'form': form})

@login_required
def book_virtual_consultation(request):
    if not hasattr(request.user, 'patient_profile'):
        return redirect('home')

    patient_profile = request.user.patient_profile

    if request.method == 'POST':
        form = AppointmentForm(request.POST, patient=patient_profile)
        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.patient = patient_profile
            appointment.consultation_type = 'Virtual'
            appointment.save()
            messages.success(request, "Your virtual consultation has been booked.")
            return redirect('appointments:appointment_list')
    else:
        form = AppointmentForm(patient=patient_profile)

    return render(request, 'appointments/book_virtual_consultation.html', {'form': form})

@login_required
def appointment_list(request):
    """Patient's Active Dashboard for managing upcoming appointments."""
    if not hasattr(request.user, 'patient_profile'):
        return redirect('home')

    patient_profile = request.user.patient_profile
    # Show only upcoming/today's appointments in the active management list
    appointments = Appointment.objects.filter(
        patient=patient_profile,
        date__gte=date.today()
    ).order_by('date', 'time')

    if request.method == 'POST':
        appointment_id = request.POST.get('appointment_id')
        action = request.POST.get('action')

        if appointment_id and action:
            appointment = get_object_or_404(Appointment, id=appointment_id, patient=patient_profile)

            if action == 'cancel':
                appointment.status = 'Cancelled'
                appointment.save()
                messages.success(request, "Appointment successfully cancelled.")

            elif action == 'reschedule':
                form = RescheduleAppointmentForm(request.POST)
                if form.is_valid():
                    appointment.status = 'Rescheduled'
                    # Assuming you have fields for these, or you are updating date/time directly
                    appointment.date = form.cleaned_data['new_date']
                    appointment.time = form.cleaned_data['new_time']
                    appointment.save()
                    messages.success(request, "Appointment successfully rescheduled.")
                else:
                    messages.error(request, "Invalid reschedule request. Please check the date and time.")

            return redirect('appointments:appointment_list')

    return render(request, 'appointments/appointment_list.html', {'appointments': appointments})

@login_required
def consultation_history(request):
    """Patient's Archive for past appointments."""
    if not hasattr(request.user, 'patient_profile'):
        return redirect('home')

    patient_profile = request.user.patient_profile
    today = date.today()

    past_appointments = Appointment.objects.filter(
        patient=patient_profile,
        date__lt=today
    ).order_by('-date', '-time')

    return render(request, 'appointments/consultation_history.html', {
        'past_appointments': past_appointments,
    })


@login_required
def add_consultation_note(request, appointment_id):
    # Security: Ensure only staff can access this
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    staff_profile = request.user.staff_profile
    appointment = get_object_or_404(Appointment, id=appointment_id)

    # FIX: Compare the appointment's doctor to the staff_profile, not the base User
    if appointment.doctor != staff_profile:
        messages.error(request, "Unauthorized: You are not the assigned doctor for this consultation.")
        return redirect('staff:staff_dashboard')  # Or wherever your default staff route is

    if request.method == 'POST':
        note = request.POST.get('note')
        prescription = request.POST.get('prescription')
        treatment_plan = request.POST.get('treatment_plan')

        # Basic validation to ensure the doctor doesn't submit a completely empty record
        if note:
            ConsultationNote.objects.create(
                appointment=appointment,
                doctor=staff_profile,  # FIX: Save the staff_profile instance
                note=note,
                prescription=prescription,
                treatment_plan=treatment_plan
            )
            messages.success(request, "Consultation notes saved securely to the patient's file.")
            # Adjust namespace if your view_appointment URL is named differently
            return redirect('staff:view_appointment', appointment_id=appointment.id)
        else:
            messages.error(request, "The primary clinical note cannot be empty.")

    return render(request, 'staff/add_consultation_note.html', {'appointment': appointment})
import os
from datetime import date

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from .forms import *
from .models import *
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from staff.models import DoctorPatientMessage, Report, Appointment
from django.contrib import messages
from django.http import FileResponse, Http404


def landing(request):
    context = {
        'hospital_name': 'CareFirst Medical Center' # Example dynamic data
    }
    return render(request, 'patients/landing.html', context)


def register(request):
    if request.method == 'POST':
        # Instantiate both forms with the POST data
        user_form = UserRegistrationForm(request.POST)
        profile_form = ProfileForm(request.POST)

        # Both forms must be valid to proceed
        if user_form.is_valid() and profile_form.is_valid():
            # 1. Save the User securely
            # NOTE: The moment user.save() runs, your signals.py creates a blank PatientProfile!
            user = user_form.save(commit=False)
            user.set_password(user_form.cleaned_data['password'])
            user.save()

            # 2. Fetch the blank profile that the signal just created
            profile = PatientProfile.objects.get(user=user)

            # 3. Update the blank profile with the data the patient typed into the form
            for field, value in profile_form.cleaned_data.items():
                setattr(profile, field, value)

            # 4. Save the updated profile
            profile.save()

            messages.success(request, 'Account created successfully! You can now log in.')
            return redirect('patients:login')
        else:
            # If validation fails, Django will automatically display the errors on the forms
            messages.error(request, 'Please correct the errors below.')
    else:
        # GET request: send empty forms
        user_form = UserRegistrationForm()
        profile_form = ProfileForm()

    return render(request, 'patients/register.html', {
        'user_form': user_form,
        'profile_form': profile_form
    })


def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']

            # authenticate() verifies the credentials against the database
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.first_name or user.username}!')
                return redirect('patients:home')
            else:
                # Provide feedback if credentials are wrong
                messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()

    return render(request, 'patients/login.html', {'form': form})


def logout_view(request):
    # Check if the logged-in user has a Profile (i.e., is a patient)
    try:
        # Attempt to access the Profile using the related_name 'profile'
        profile = request.user.Patient.profile  # This will raise an exception if no Profile exists

        # If the user has a Profile, they are a patient
        logout(request)
        return redirect('patients:login')

    except ObjectDoesNotExist:
        # If no Profile exists for the user, they are not a patient
        logout(request)


@login_required
def home(request):
    patient_profile = request.user.patient_profile

    # Fetch the next 3 upcoming, scheduled appointments
    upcoming_appointments = Appointment.objects.filter(
        patient=patient_profile,
        date__gte=date.today(),
        status='Scheduled'
    ).order_by('date', 'time')[:3]

    context = {
        'upcoming_appointments': upcoming_appointments,
    }
    return render(request, 'patients/home.html', context)


# Profile View
@login_required
def profile(request):
    # Fetch directly using the one-to-one related_name we established
    patient_profile = request.user.patient_profile

    return render(request, 'patients/profile.html', {'profile': patient_profile})


@login_required
def update_profile(request):
    patient_profile = request.user.patient_profile

    if request.method == 'POST':
        # Pass the existing profile instance so Django knows to UPDATE, not create
        form = ProfileForm(request.POST, instance=patient_profile)
        if form.is_valid():
            form.save()
            # Add a success message for a better user experience
            messages.success(request, "Your medical profile has been updated successfully.")
            return redirect('patients:profile')
    else:
        # Pre-fill the form with the user's current data
        form = ProfileForm(instance=patient_profile)

    return render(request, 'patients/update_profile.html', {
        'form': form,
        'profile': patient_profile
    })


@login_required
def medication_reminders(request):
    patient_profile = request.user.patient_profile

    # Handle the patient checking off a medication
    if request.method == 'POST':
        reminder_id = request.POST.get('reminder_id')
        if reminder_id:
            # Ensure the reminder actually belongs to this patient
            reminder = get_object_or_404(MedicationReminder, id=reminder_id, patient=patient_profile)
            # Toggle the status (if False it becomes True, and vice versa)
            reminder.is_taken = not reminder.is_taken
            reminder.save()
            return redirect('appointments:medication_reminders')  # Adjust namespace if needed

    # Fetch reminders and order them chronologically by time
    reminders = MedicationReminder.objects.filter(patient=patient_profile).order_by('time')

    return render(request, 'appointments/medication_reminders.html', {'reminders': reminders})


@login_required
# def bill_list(request):
#     bills = Bill.objects.filter(patient=request.user)
#     return render(request, 'appointments/bill_list.html', {'bills': bills})


@login_required
def feedback_form(request):
    if request.method == 'POST':
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            # FIX: Use the updated related_name for the unified profile
            feedback.patient = request.user.patient_profile
            feedback.save()

            # UX Enhancement: Flash a success message and send them to the dashboard
            messages.success(request, "Thank you! Your feedback helps us improve our care.")
            return redirect('patients:home')
    else:
        form = FeedbackForm()

    return render(request, 'appointments/feedback_form.html', {'form': form})


@login_required
def treatment_plans(request):
    # Fixed the relationship and ordered by most recent first
    plans = TreatmentPlan.objects.filter(
        patient=request.user.patient_profile
    ).order_by('-start_date')

    return render(request, 'appointments/treatment_plans.html', {'plans': plans})


@login_required
def emergency_contact(request):
    patient_profile = request.user.patient_profile

    # Fetch all emergency requests, ordered by the most recent
    emergency_requests = EmergencyService.objects.filter(
        patient=patient_profile
    ).order_by('-request_time')

    # Grab the latest one to show current status, and pass the rest as history
    latest_emergency = emergency_requests.first()

    return render(request, 'appointments/emergency_contact.html', {
        'profile': patient_profile,  # Passed the profile to show the actual emergency contacts
        'latest_emergency': latest_emergency,
        'emergency_history': emergency_requests[1:5]  # Show the last 4 historical requests
    })


# This is for the patient viewing messages
@login_required
def patient_messages(request):
    # Fetch messages sent to the logged-in patient
    # Ordered by the most recent message first
    user_messages = DoctorPatientMessage.objects.filter(
        recipient=request.user.patient_profile
    ).order_by('-sent_at')

    return render(request, 'patients/patient_messages.html', {'messages': user_messages})


@login_required
def view_message(request, message_id):
    # Security: Ensure the message exists and belongs to the logged-in patient
    message = get_object_or_404(
        DoctorPatientMessage,
        id=message_id,
        recipient=request.user.patient_profile
    )

    if request.method == 'POST':
        reply_content = request.POST.get('patient_reply')

        if reply_content:
            message.patient_reply = reply_content
            message.save()
            messages.success(request, "Your reply has been sent to the doctor.")
            return redirect('patients:patient_messages')
        else:
            messages.error(request, "Reply content cannot be empty.")

    return render(request, 'patients/view_messages.html', {'message': message})


@login_required
def report_list(request):
    # Fetching reports for the optimized patient_profile relationship
    reports = Report.objects.filter(
        generated_for=request.user.patient_profile
    ).order_by('-generated_at')

    return render(request, 'patients/report_list.html', {'reports': reports})


@login_required
def report_detail(request, report_id):
    # Securely fetch the report belonging only to this patient
    report = get_object_or_404(
        Report,
        id=report_id,
        generated_for=request.user.patient_profile
    )
    return render(request, 'patients/report_detail.html', {'report': report})


@login_required
def download_report(request, report_id):
    report = get_object_or_404(
        Report,
        id=report_id,
        generated_for=request.user.patient_profile
    )

    # Ensure the file path exists on the storage before opening
    if not report.file_path or not os.path.exists(report.file_path.path):
        raise Http404("The requested PDF file does not exist on the server.")

    # Open the file in binary mode
    response = FileResponse(
        open(report.file_path.path, 'rb'),
        content_type='application/pdf'
    )
    # This header suggests the browser download the file rather than just viewing it
    response['Content-Disposition'] = f'attachment; filename="{report.title}.pdf"'
    return response
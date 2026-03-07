# views.py
import os

from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404, reverse
from django.contrib.auth.forms import *
from django.contrib.auth import login, authenticate
from django.http import HttpResponseForbidden, Http404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from .models import *
from django.utils import timezone
from .forms import *
from django.http import FileResponse
from django.contrib.auth import logout
from django.contrib import messages
from patients.models import PatientProfile
from urllib.parse import urlencode
from django.utils.timezone import now
from datetime import timedelta, datetime, date
from staff.models import Appointment as APP
from django.core.exceptions import ValidationError

DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']


def register(request):
    if request.method == 'POST':
        form = StaffUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('staff:login')
        else:
            logger.warning("Staff registration form invalid: %s", form.errors)
    else:
        form = StaffUserCreationForm()

    return render(request, 'staff/register.html', {'form': form})


def login_view(request):
    # Redirect already-authenticated users away from the login page
    if request.user.is_authenticated:
        return redirect('staff:dashboard')

    alert_message = request.GET.get('alert_message')

    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('staff:dashboard')
        else:
            logger.warning("Staff login failed for user: %s", request.POST.get('username'))
    else:
        form = AuthenticationForm()

    return render(request, 'staff/login.html', {
        'form': form,
        'alert_message': alert_message,
    })


def logout_view(request):
    alert_message = None

    if request.user.is_authenticated:
        try:
            staff_profile = Staff.objects.get(user=request.user)
            role_display = {
                'doctor': 'a Doctor',
                'nurse': 'a Nurse',
                'admin': 'an Administrator',
            }.get(staff_profile.role, 'a Staff Member')
            alert_message = f"You have been logged out as {role_display}."
        except Staff.DoesNotExist:
            logger.warning("No Staff profile found for user: %s", request.user.username)
            alert_message = "You have been logged out."

        logout(request)

    url = reverse('staff:login')
    if alert_message:
        query_params = urlencode({'alert_message': alert_message})
        return redirect(f"{url}?{query_params}")

    return redirect(url)

ROLE_TEMPLATES = {
    'doctor': 'staff/doctor_dashboard.html',
    'nurse':  'staff/nurse_dashboard.html',
    'admin':  'staff/admin_dashboard.html',
}


@login_required
def staff_dashboard(request):
    try:
        staff = request.user.staff_profile
    except AttributeError:
        return HttpResponseForbidden("No staff profile is linked to your account.")

    template = ROLE_TEMPLATES.get(staff.role)
    if not template:
        return HttpResponseForbidden("You don't have permission to view this page.")

    return render(request, template, {'staff': staff})


def is_doctor(user):
    return user.staff.role == 'doctor'


@user_passes_test(is_doctor)
def doctor_view(request):
    # Doctor-specific view logic
    return render(request, 'staff/doctor_page.html')


@login_required
def doctor_schedule(request):
    # Role guard
    if not hasattr(request.user, 'staff_profile') or request.user.staff_profile.role != 'doctor':
        return redirect('staff:unauthorized')

    doctor = request.user.staff_profile

    # get_or_create by doctor only — don't mix in `id=request.user.id`
    schedule, _ = DoctorSchedule.objects.get_or_create(doctor=doctor)

    if request.method == 'POST':
        validation_failed = False

        for day in DAYS:
            start_time = request.POST.get(f'{day}_start') or None
            end_time   = request.POST.get(f'{day}_end')   or None

            if start_time and end_time:
                if start_time >= end_time:
                    messages.error(request, f"{day.capitalize()}: start time must be earlier than end time.")
                    validation_failed = True
                    break
                setattr(schedule, f'{day}_start', start_time)
                setattr(schedule, f'{day}_end',   end_time)

            elif start_time or end_time:
                messages.error(request, f"{day.capitalize()}: both start and end times are required, or leave both blank.")
                validation_failed = True
                break

            else:
                # Both blank — clear the day
                setattr(schedule, f'{day}_start', None)
                setattr(schedule, f'{day}_end',   None)

        if not validation_failed:
            try:
                schedule.full_clean()
                schedule.save()
                messages.success(request, "Your schedule has been updated.")
                return redirect('staff:doctor_schedule')
            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")

    # Build schedule_data for the template — always from the (possibly unsaved) schedule object
    schedule_data = {
        day: {
            'start': getattr(schedule, f'{day}_start') or '',
            'end':   getattr(schedule, f'{day}_end')   or '',
        }
        for day in DAYS
    }

    return render(request, 'staff/doctor_schedule.html', {
        'schedule':      schedule,
        'days':          DAYS,          # lowercase — template handles capitalisation
        'schedule_data': schedule_data,
    })


def unauthorized(request):
    return render(request, 'staff/unauthorized.html', status=403)


@login_required
def assign_appointment(request, patient_id):
    patient = get_object_or_404(PatientProfile, id=patient_id)
    available_doctors = Staff.objects.filter(role='doctor').select_related('user', 'doctor_schedule')

    if request.method == 'POST':
        reason        = request.POST.get('reason', '').strip()
        date_time_str = request.POST.get('date_time', '')
        doctor_id     = request.POST.get('doctor')

        # ── Basic field validation ──────────────────────────────────────────
        if not reason:
            messages.error(request, "Please provide a reason for the appointment.")
            return render(request, 'staff/assign_appointment.html', {
                'patient': patient, 'doctors': available_doctors,
            })

        try:
            date_time = datetime.strptime(date_time_str, '%Y-%m-%dT%H:%M')
        except (ValueError, TypeError):
            messages.error(request, "Invalid date/time format.")
            return render(request, 'staff/assign_appointment.html', {
                'patient': patient, 'doctors': available_doctors,
            })

        if date_time < datetime.now():
            messages.error(request, "Appointment time must be in the future.")
            return render(request, 'staff/assign_appointment.html', {
                'patient': patient, 'doctors': available_doctors,
            })

        # ── Resolve doctor ──────────────────────────────────────────────────
        # If a specific doctor was chosen in the form, use them.
        # Otherwise fall back to auto-assigning the first available doctor.
        if doctor_id:
            doctors_to_check = available_doctors.filter(id=doctor_id)
            if not doctors_to_check.exists():
                messages.error(request, "Selected doctor not found.")
                return render(request, 'staff/assign_appointment.html', {
                    'patient': patient, 'doctors': available_doctors,
                })
        else:
            doctors_to_check = available_doctors

        if not doctors_to_check.exists():
            messages.error(request, "No doctors are available.")
            return render(request, 'staff/assign_appointment.html', {
                'patient': patient, 'doctors': available_doctors,
            })

        # ── Check schedule & conflicts ──────────────────────────────────────
        day_of_week = date_time.strftime('%A').lower()

        for doctor in doctors_to_check:
            schedule = getattr(doctor, 'doctor_schedule', None)
            if not schedule:
                continue

            start_time = getattr(schedule, f"{day_of_week}_start", None)
            end_time   = getattr(schedule, f"{day_of_week}_end",   None)

            if not (start_time and end_time):
                continue  # Doctor not working that day

            if not (start_time <= date_time.time() <= end_time):
                continue  # Outside working hours

            # Check for overlapping appointments (30-minute slots)
            conflict = Appointment.objects.filter(
                doctor=doctor,
                scheduled_time__gte=date_time,
                scheduled_time__lt=date_time + timedelta(minutes=30),
            ).exists()

            if conflict:
                continue

            # ── All checks passed — create the appointment ──────────────────
            Appointment.objects.create(
                patient=patient,
                doctor=doctor,
                created_by=request.user.staff_profile,
                scheduled_time=date_time,
                reason=reason,
                status='scheduled',
            )
            messages.success(
                request,
                f"Appointment scheduled with Dr. {doctor.user.get_full_name() or doctor.user.username} "
                f"on {date_time.strftime('%A, %d %B %Y at %H:%M')}."
            )
            return redirect('staff:display_patient', patient_id=patient.id)

        # If we exhaust all doctors without booking
        messages.error(request, "No doctors are available at the selected time. Please choose a different slot.")
        return render(request, 'staff/assign_appointment.html', {
            'patient': patient, 'doctors': available_doctors,
            'posted_reason': reason, 'posted_datetime': date_time_str,
            'posted_doctor': doctor_id,
        })

    return render(request, 'staff/assign_appointment.html', {
        'patient': patient,
        'doctors': available_doctors,
    })


@login_required
def view_appointment(request, appointment_id):
    # Exclude cancelled appointments — status__ne is not valid Django ORM
    appointment = get_object_or_404(
        Appointment.objects.select_related(
            'patient__user', 'doctor__user', 'created_by__user'
        ),
        id=appointment_id,
    )

    if appointment.status.lower() == 'cancelled':
        return redirect('staff:dashboard')

    # Only the assigned doctor or an admin may view this page
    staff = getattr(request.user, 'staff_profile', None)
    if staff is None:
        return redirect('staff:unauthorized')

    is_assigned_doctor = (appointment.doctor == staff)
    is_admin = (staff.role == 'admin')

    if not (is_assigned_doctor or is_admin):
        return redirect('staff:unauthorized')

    note = ConsultationNote.objects.filter(appointment=appointment).first()

    return render(request, 'staff/view_appointment.html', {
        'appointment':       appointment,
        'note':              note,
        'is_assigned_doctor': is_assigned_doctor,
    })


@login_required
def view_patient_appointments(request, patient_id):
    patient = get_object_or_404(
        PatientProfile.objects.select_related('user'),
        id=patient_id,
    )

    appointments = (
        Appointment.objects
        .filter(patient=patient)
        .select_related('doctor__user')
        .order_by('-time')
    )

    return render(request, 'staff/patient_appointments.html', {
        'patient':      patient,
        'appointments': appointments,
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


@login_required
def patient_assignments(request):
    # Security: Ensure user is a staff member
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    staff_profile = request.user.staff_profile

    # Fetch active patients assigned to this specific doctor/staff
    assignments = Assignment.objects.filter(
        doctor=staff_profile
    ).order_by('-assigned_at')  # Assuming you have a date field

    return render(request, 'staff/patient_assignments.html', {'assignments': assignments})


@login_required
def manage_patient_assignment(request, assignment_id):
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    staff_profile = request.user.staff_profile

    # Ensure the doctor can only manage their OWN assigned patients
    assignment = get_object_or_404(Assignment, id=assignment_id, doctor=staff_profile)

    if request.method == 'POST':
        notes = request.POST.get('notes')
        if notes is not None:
            assignment.notes = notes
            assignment.save()
            messages.success(request, f"Assignment notes for {assignment.patient.user.last_name} updated successfully.")
            return redirect('staff:patient_assignments')

    return render(request, 'staff/manage_patient_assignment.html', {'assignment': assignment})


# View to search for a patient by username or email
@login_required
def search_patient(request):
    query = request.GET.get('q', '').strip()

    if query:
        patients = (
            PatientProfile.objects
            .filter(
                Q(user__username__icontains=query)
                | Q(user__email__icontains=query)
                | Q(user__first_name__icontains=query)
                | Q(user__last_name__icontains=query)
            )
            .select_related('user')
            .distinct()
        )
    else:
        patients = PatientProfile.objects.select_related('user').all()

    return render(request, 'staff/search_patient.html', {
        'patients': patients,
        'query':    query,
    })


@login_required
def display_patient(request, patient_id):
    patient = get_object_or_404(
        PatientProfile.objects.select_related('user'),
        id=patient_id,
    )

    context = {
        'patient':          patient,
        'vitals':           VitalSign.objects.filter(patient=patient).order_by('-id')[:5],
        'progress_reports': ProgressTracking.objects.filter(patient=patient).order_by('-id')[:5],
        'care_plans':       CarePlan.objects.filter(patient=patient),
        'medical_records':  MedicalRecord.objects.filter(patient=patient).order_by('-id')[:5],
        'lab_tests':        LabTest.objects.filter(patient=patient).order_by('-id')[:5],
        'prescriptions':    Prescription.objects.filter(patient=patient).order_by('-id')[:5],
        'upcoming_appointments': (
            Appointment.objects
            .filter(patient=patient)
            .exclude(status='cancelled')
            .select_related('doctor__user')
            .order_by('time')[:3]
        ),
    }

    return render(request, 'staff/display_patient.html', context)


@login_required
def add_vitals(request, patient_id):
    patient = get_object_or_404(PatientProfile.objects.select_related('user'), id=patient_id)
    errors = {}

    if request.method == 'POST':
        vital_sign = VitalSign(
            patient=patient,
            blood_pressure=request.POST.get('blood_pressure', '').strip(),
            temperature=request.POST.get('temperature') or None,
            pulse=request.POST.get('pulse') or None,
            weight=request.POST.get('weight') or None,
            oxygen_saturation=request.POST.get('oxygen_saturation') or None,
            recorded_by=request.user.staff_profile,
        )
        try:
            vital_sign.full_clean()
            vital_sign.save()
            return redirect('staff:view_vitals', patient_id=patient.id)
        except ValidationError as e:
            errors = e.message_dict

    return render(request, 'staff/add_vitals.html', {
        'patient': patient,
        'errors':  errors,
        # Re-populate form on error
        'posted': request.POST if request.method == 'POST' else {},
    })


@login_required
def add_progress_tracking(request, patient_id):
    patient = get_object_or_404(PatientProfile.objects.select_related('user'), id=patient_id)
    error = None

    if request.method == 'POST':
        progress_notes = request.POST.get('progress_notes', '').strip()
        if not progress_notes:
            error = "Progress notes cannot be empty."
        else:
            ProgressTracking.objects.create(
                patient=patient,
                doctor=request.user.staff_profile,  # was request.user — wrong model
                progress_notes=progress_notes,
            )
            return redirect('staff:view_progress_tracking', patient_id=patient.id)

    return render(request, 'staff/add_progress_tracking.html', {
        'patient': patient,
        'error':   error,
        'posted':  request.POST if request.method == 'POST' else {},
    })


@login_required
def view_vitals(request, patient_id):
    patient = get_object_or_404(PatientProfile.objects.select_related('user'), id=patient_id)
    vitals = (
        VitalSign.objects
        .filter(patient=patient)
        .select_related('recorded_by__user')
        .order_by('-recorded_at')
    )
    return render(request, 'staff/view_vitals.html', {   # was 'view_vitals.html' — missing 'staff/' prefix
        'patient': patient,
        'vitals':  vitals,
    })


@login_required
def view_progress_tracking(request, patient_id):
    patient = get_object_or_404(PatientProfile.objects.select_related('user'), id=patient_id)
    progress_reports = (
        ProgressTracking.objects
        .filter(patient=patient)
        .select_related('doctor__user')
        .order_by('-recorded_at')
    )
    return render(request, 'staff/view_progress_tracking.html', {
        'patient':          patient,
        'progress_reports': progress_reports,
    })


@login_required
def add_care_plan(request, patient_id):
    patient = get_object_or_404(PatientProfile.objects.select_related('user'), id=patient_id)
    error = None

    if request.method == 'POST':
        plan_description = request.POST.get('plan_description', '').strip()
        if not plan_description:
            error = "Care plan description cannot be empty."
        else:
            CarePlan.objects.create(
                patient=patient,
                doctor=request.user.staff_profile,  # was request.user — wrong model
                plan_description=plan_description,
            )
            return redirect('staff:view_care_plan', patient_id=patient.id)

    return render(request, 'staff/add_care_plan.html', {
        'patient': patient,
        'error':   error,
        'posted':  request.POST if request.method == 'POST' else {},
    })


@login_required
def view_care_plan(request, patient_id):
    patient = get_object_or_404(PatientProfile.objects.select_related('user'), id=patient_id)
    care_plans = (
        CarePlan.objects
        .filter(patient=patient)
        .select_related('doctor__user')
        .order_by('-created_at')
    )
    return render(request, 'staff/view_care_plan.html', {
        'patient':    patient,
        'care_plans': care_plans,
    })


@login_required
def add_medical_record(request, patient_id):
    patient = get_object_or_404(PatientProfile.objects.select_related('user'), id=patient_id)
    errors = {}

    if request.method == 'POST':
        fields = {
            'diagnoses':         request.POST.get('diagnoses', '').strip(),
            'treatment_history': request.POST.get('treatment_history', '').strip(),
            'allergies':         request.POST.get('allergies', '').strip(),
            'family_history':    request.POST.get('family_history', '').strip(),
            'medications':       request.POST.get('medications', '').strip(),
        }

        if not fields['diagnoses']:
            errors['diagnoses'] = "Diagnoses field is required."

        if not errors:
            MedicalRecord.objects.create(patient=patient, **fields)
            return redirect('staff:view_medical_record', patient_id=patient.id)

    return render(request, 'staff/add_medical_record.html', {
        'patient': patient,
        'errors':  errors,
        'posted':  request.POST if request.method == 'POST' else {},
    })


@login_required
def view_medical_record(request, patient_id):
    patient = get_object_or_404(PatientProfile.objects.select_related('user'), id=patient_id)
    medical_records = (
        MedicalRecord.objects
        .filter(patient=patient)
        .order_by('-id')
    )
    return render(request, 'staff/view_medical_record.html', {
        'patient':         patient,
        'medical_records': medical_records,
    })


@login_required
def order_lab_test(request, patient_id):
    patient = get_object_or_404(PatientProfile.objects.select_related('user'), id=patient_id)
    error = None

    if request.method == 'POST':
        test_name = request.POST.get('test_name', '').strip()
        notes     = request.POST.get('notes', '').strip()

        if not test_name:
            error = "Test name is required."
        else:
            LabTest.objects.create(
                patient=patient,
                test_name=test_name,
                notes=notes or None,
                ordered_by=request.user.staff_profile,  # was request.user — wrong model
                status='ordered',
            )
            return redirect('staff:view_lab_tests', patient_id=patient.id)  # was missing namespace

    return render(request, 'staff/order_lab_test.html', {
        'patient': patient,
        'error':   error,
        'posted':  request.POST if request.method == 'POST' else {},
    })


@login_required
def view_lab_tests(request, patient_id):
    patient = get_object_or_404(PatientProfile.objects.select_related('user'), id=patient_id)
    lab_tests = (
        LabTest.objects
        .filter(patient=patient)
        .select_related('ordered_by__user', 'result')   # avoids N+1 on result access
        .order_by('-id')
    )
    return render(request, 'staff/view_lab_tests.html', {
        'patient':   patient,
        'lab_tests': lab_tests,
    })


@login_required
def add_lab_result(request, lab_test_id):
    lab_test = get_object_or_404(
        LabTest.objects.select_related('patient__user'),
        id=lab_test_id,
    )
    error = None

    if lab_test.status == 'completed':
        # Guard: don't let a result be added twice
        return redirect('staff:view_lab_tests', patient_id=lab_test.patient.id)

    if request.method == 'POST':
        result_data = request.POST.get('result_data', '').strip()
        findings    = request.POST.get('findings', '').strip()

        if not result_data:
            error = "Result data is required."
        else:
            LabResult.objects.create(
                lab_test=lab_test,
                result_data=result_data,
                findings=findings or None,
            )
            lab_test.status = 'completed'
            lab_test.save(update_fields=['status'])   # only update the status column
            return redirect('staff:view_lab_tests', patient_id=lab_test.patient.id)

    return render(request, 'staff/add_lab_result.html', {
        'lab_test': lab_test,
        'error':    error,
        'posted':   request.POST if request.method == 'POST' else {},
    })


@login_required
def prescribe_medication(request, patient_id):
    patient = get_object_or_404(PatientProfile.objects.select_related('user'), id=patient_id)
    errors = {}

    if request.method == 'POST':
        medication_name = request.POST.get('medication_name', '').strip()
        dosage          = request.POST.get('dosage', '').strip()
        end_date_str    = request.POST.get('end_date', '').strip()
        instructions    = request.POST.get('instructions', '').strip()
        start_date_str  = request.POST.get('start_date', '').strip()

        # ── Validation ────────────────────────────────────────────
        if not medication_name:
            errors['medication_name'] = "Medication name is required."
        if not dosage:
            errors['dosage'] = "Dosage is required."

        end_date = None
        if end_date_str:
            try:
                end_date = date.fromisoformat(end_date_str)
                if end_date < date.today():
                    errors['end_date'] = "End date cannot be in the past."
            except ValueError:
                errors['end_date'] = "Invalid date format."

        start_date = None
        if start_date_str:
            try:
                start_date = date.fromisoformat(start_date_str)
            except ValueError:
                errors['start_date'] = "Invalid date format."

        if start_date and end_date and start_date > end_date:
            errors['end_date'] = "End date must be after the start date."

        if not errors:
            Prescription.objects.create(
                patient=patient,
                doctor=request.user.staff_profile,   # was request.user — wrong model
                medication_name=medication_name,
                dosage=dosage,
                start_date=start_date,
                end_date=end_date,
                instructions=instructions or None,
            )
            return redirect('staff:view_prescriptions', patient_id=patient.id)

    return render(request, 'staff/prescribe_medication.html', {
        'patient': patient,
        'errors':  errors,
        'posted':  request.POST if request.method == 'POST' else {},
        'today':   date.today().isoformat(),
    })


@login_required
def view_prescriptions(request, patient_id):
    patient = get_object_or_404(PatientProfile.objects.select_related('user'), id=patient_id)
    prescriptions = (
        Prescription.objects
        .filter(patient=patient)
        .select_related('doctor__user')
        .order_by('-id')
    )
    today = date.today()
    return render(request, 'staff/view_prescriptions.html', {
        'patient':       patient,
        'prescriptions': prescriptions,
        'today':         today,
    })


@login_required
def staff_messages(request):
    """Overview: shows sent + received counts and recent activity."""
    try:
        current_staff = Staff.objects.get(user=request.user)
    except Staff.DoesNotExist:
        messages.error(request, "Staff profile not found.")
        return redirect('staff:dashboard')

    inbox = (
        StaffMessage.objects
        .filter(recipient=current_staff)
        .select_related('sender__user')
        .order_by('-sent_at')[:5]
    )
    sent = (
        StaffMessage.objects
        .filter(sender=current_staff)
        .select_related('recipient__user')
        .order_by('-sent_at')[:5]
    )
    unread_count = StaffMessage.objects.filter(recipient=current_staff, is_read=False).count()

    return render(request, 'staff/staff_messages.html', {
        'inbox':        inbox,
        'sent':         sent,
        'unread_count': unread_count,
        'current_staff': current_staff,
    })


@login_required
def send_staff_message(request):
    staff_members = Staff.objects.exclude(user=request.user).select_related('user')

    if request.method == 'POST':
        recipient_id    = request.POST.get('recipient_id', '').strip()
        message_content = request.POST.get('message_content', '').strip()

        if not recipient_id or not message_content:
            messages.error(request, "Please fill in all fields.")
        else:
            try:
                recipient = Staff.objects.get(id=recipient_id)
                sender    = Staff.objects.get(user=request.user)  # raises if no staff profile

                StaffMessage.objects.create(
                    sender=sender,
                    recipient=recipient,
                    message_content=message_content,
                )
                messages.success(
                    request,
                    f"Message sent to {recipient.user.get_full_name() or recipient.user.username}."
                )
                return redirect('staff:staff_inbox')  # go to inbox, not back to compose

            except Staff.DoesNotExist:
                messages.error(request, "Recipient not found.")

    return render(request, 'staff/send_staff_message.html', {
        'staff_members': staff_members,
        'posted': request.POST if request.method == 'POST' else {},
    })


@login_required
def staff_inbox(request):
    try:
        current_staff = Staff.objects.get(user=request.user)
    except Staff.DoesNotExist:
        messages.error(request, "Staff profile not found.")
        return redirect('staff:dashboard')

    # 'messages' was shadowed by the Django messages import — renamed to inbox_messages
    inbox_messages = (
        StaffMessage.objects
        .filter(recipient=current_staff)
        .select_related('sender__user')
        .order_by('-sent_at')
    )
    unread_count = inbox_messages.filter(is_read=False).count()

    return render(request, 'staff/staff_inbox.html', {
        'inbox_messages': inbox_messages,   # was 'messages' — clashes with Django messages framework
        'unread_count':   unread_count,
    })


@login_required
def message_detail(request, message_id):
    try:
        current_staff = Staff.objects.get(user=request.user)
    except Staff.DoesNotExist:
        messages.error(request, "Staff profile not found.")
        return redirect('staff:dashboard')

    # Use get_object_or_404 — avoids bare try/except on DoesNotExist
    message = get_object_or_404(
        StaffMessage.objects.select_related('sender__user', 'recipient__user'),
        id=message_id,
        recipient=current_staff,   # was recipient__user=request.user, which skips the Staff lookup
    )

    if not message.is_read:
        message.is_read = True
        message.read_at = now()
        message.save(update_fields=['is_read', 'read_at'])

    return render(request, 'staff/message_detail.html', {'message': message})


# request.user.staff_profile.role
@login_required
def doctor_patient_messages(request, patient_id):
    # Security: Ensure only staff with 'doctor' role can access
    staff_profile = getattr(request.user, 'staff_profile', None)
    if not staff_profile or staff_profile.role != 'doctor':
        return HttpResponseForbidden("Only doctors can access patient messaging.") # Changed to Forbidden for better security UX

    # Fetch the patient using the updated model
    patient = get_object_or_404(PatientProfile, id=patient_id)

    # Get conversation history
    chat_history = DoctorPatientMessage.objects.filter(
        recipient=patient,
        sender=staff_profile
    ).order_by('sent_at')

    # FIX: Query records using the 'patient' object we just fetched, NOT the logged-in doctor!
    records = MedicalRecord.objects.filter(
        patient=patient
    ).order_by('-created_at') # Make sure this matches your model's date field (e.g., date_recorded)

    if request.method == 'POST':
        form = DoctorPatientMessageForm(request.POST)
        if form.is_valid():
            new_msg = form.save(commit=False)
            new_msg.sender = staff_profile
            new_msg.recipient = patient
            new_msg.save()
            messages.success(request, "Message dispatched to patient.")
            return redirect('staff:doctor_patient_messages', patient_id=patient_id)
    else:
        form = DoctorPatientMessageForm()

    return render(request, 'staff/doctor_patient_messages.html', {
        'messages': chat_history,
        'patient': patient,
        'form': form,
        'records': records
    })


@login_required
def staff_patient_records(request, patient_id):
    # 1. Security: Ensure only doctors can access this
    staff = getattr(request.user, 'staff_profile', None)
    if not staff or staff.role != 'doctor':
        return HttpResponseForbidden("Security Protocol: Only authorized doctors can view full medical files.")

    # 2. Fetch the specific patient they clicked on
    patient = get_object_or_404(PatientProfile, id=patient_id)

    # 3. Fetch that specific patient's medical records
    records = MedicalRecord.objects.filter(patient=patient).order_by('-date_recorded')

    return render(request, 'staff/patient_medical_records.html', {
        'patient': patient,
        'records': records
    })

@login_required
def team_collaboration(request, patient_id):
    # Ensure user is staff
    staff_profile = getattr(request.user, 'staff_profile', None)
    if not staff_profile:
        return redirect('patients:home')

    patient = get_object_or_404(PatientProfile, id=patient_id)

    # Internal messages where the current staff is either sender OR recipient
    # specifically regarding this patient's case (if you had a patient FK)
    # Since your model doesn't have a patient FK, we'll show general team messages for now
    messages = TeamMessage.objects.filter(
        models.Q(sender=staff_profile) | models.Q(recipient=staff_profile)
    ).order_by('-sent_at')

    if request.method == 'POST':
        form = TeamMessageForm(request.POST, exclude_user=request.user)
        if form.is_valid():
            msg = form.save(commit=False)
            msg.sender = staff_profile
            msg.save()
            return redirect('staff:team_collaboration', patient_id=patient_id)
    else:
        form = TeamMessageForm(exclude_user=request.user)

    return render(request, 'staff/team_collaboration.html', {
        'messages': messages,
        'patient': patient,
        'form': form
    })


@login_required
def insurance_verification(request, patient_id):
    # Ensure only staff (Reception/Finance) can verify
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    try:
        # Optimized lookup using the patient_profile relationship
        insurance = Insurance.objects.get(profile__id=patient_id, verified=False)
        return render(request, 'staff/insurance_verification.html', {'insurance': insurance})
    except Insurance.DoesNotExist:
        messages.info(request, "No pending insurance found for this patient.")
        return redirect('staff:patient_list')

@login_required
def verify_insurance(request, insurance_id):
    insurance = get_object_or_404(Insurance, id=insurance_id)
    insurance.verified = True
    insurance.save()
    messages.success(request, f"Insurance for {insurance.profile.user.last_name} verified.")
    return redirect('staff:patient_detail', patient_id=insurance.profile.id)

@login_required
def bill_creation_and_tracking(request, patient_id):
    patient = get_object_or_404(PatientProfile, id=patient_id)

    if request.method == 'POST':
        form = BillForm(request.POST)
        if form.is_valid():
            bill = form.save(commit=False)
            bill.patient = patient
            bill.save()
            messages.success(request, "New bill generated successfully.")
            return redirect('staff:bill_tracking', patient_id=patient.id)
    else:
        form = BillForm()

    bills = Bill.objects.filter(patient=patient).order_by('-created_at')
    return render(request, 'staff/bill_tracking.html', {
        'bills': bills,
        'form': form,
        'patient': patient
    })

@login_required
def insurance_claim_submission(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)
    claims = InsuranceClaim.objects.filter(bill=bill).order_by('-submitted_at')

    if request.method == 'POST':
        form = InsuranceClaimForm(request.POST)
        if form.is_valid():
            claim = form.save(commit=False)
            claim.bill = bill
            claim.save()
            messages.success(request, "Insurance claim submitted.")
            return redirect('staff:insurance_claim_submission', bill_id=bill.id)
    else:
        form = InsuranceClaimForm()

    return render(request, 'staff/insurance_claim_submission.html', {
        'bill': bill,
        'claims': claims,
        'form': form
    })

@login_required
def emergency_alert_list(request):
    # Security: Only staff should see the global emergency dispatch list
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    # Fetch all alerts that aren't resolved yet, most urgent first
    active_alerts = EmergencyAlert.objects.exclude(status='resolved').order_by('-created_at')

    # Also fetch recently resolved alerts for a history log
    resolved_history = EmergencyAlert.objects.filter(status='resolved').order_by('-resolved_at')[:10]

    return render(request, 'staff/emergency_alert_list.html', {
        'alerts': active_alerts,
        'history': resolved_history
    })


@login_required
def acknowledge_alert(request, pk):
    # Ensure only authorized staff can acknowledge
    alert = get_object_or_404(EmergencyAlert, pk=pk)
    alert.status = 'acknowledged'
    alert.acknowledged_by = request.user.staff_profile  # Tracking who responded
    alert.save()

    messages.warning(request, f"Alert #{pk} has been acknowledged. Response team notified.")
    return redirect('staff:emergency_alert_list')


@login_required
def resolve_alert(request, pk):
    alert = get_object_or_404(EmergencyAlert, pk=pk)
    alert.status = 'resolved'
    alert.resolved_at = timezone.now()
    alert.save()

    messages.success(request, f"Alert #{pk} has been marked as resolved.")
    return redirect('staff:emergency_alert_list')


@login_required
def medical_supply_inventory(request):
    # Ensure only staff can view inventory
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    # Fetch all supplies and calculate stock health in the template
    supplies = MedicalSupply.objects.all().order_by('category', 'name')
    return render(request, 'staff/medical_supply_inventory.html', {'supplies': supplies})


@login_required
def stock_alerts(request):
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    # Urgent alerts first
    alerts = StockAlert.objects.filter(alert_status='unresolved').order_by('-alert_date')
    return render(request, 'staff/stock_alerts.html', {'alerts': alerts})


@login_required
def order_management(request):
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    # Track orders from newest to oldest
    orders = Order.objects.all().order_by('-order_date')
    return render(request, 'staff/order_management.html', {'orders': orders})


@login_required
def dashboard_view(request):
    metrics = HospitalPerformanceMetrics.objects.latest('updated_at')
    analytics = PerformanceAnalytics.objects.order_by('-report_date')[:5]
    return render(request, 'staff/hospital_dashboard.html', {'metrics': metrics, 'analytics': analytics})


@login_required
def resource_allocation_view(request):
    # Security: Ensure only staff can access the resource board
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    # Fetch all resources, grouped by their category for the UI
    resources = ResourceAllocation.objects.all().order_by('resource_type', 'resource_name')

    # Quick stats for the dashboard header
    total_resources = resources.count()
    available_count = resources.filter(status='Available').count()
    in_use_count = resources.filter(status='In Use').count()

    return render(request, 'staff/resource_allocation.html', {
        'resources': resources,
        'stats': {
            'total': total_resources,
            'available': available_count,
            'in_use': in_use_count,
        }
    })


@login_required
def create_report(request, patient_id):
    # Security Check
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    patient = get_object_or_404(PatientProfile, id=patient_id)

    if request.method == 'POST':
        title = request.POST.get('title')
        report_type = request.POST.get('report_type')
        # request.FILES is required to grab the actual uploaded document
        file_path = request.FILES.get('file_path')

        if title and report_type and file_path:
            Report.objects.create(
                title=title,
                report_type=report_type,
                generated_for=patient,
                generated_by=request.user.staff_profile,
                file_path=file_path,
            )
            messages.success(request, f"Document '{title}' uploaded successfully.")
            return redirect('staff:report_list', patient_id=patient.id)
        else:
            messages.error(request, "Please fill all fields and attach a valid file.")

    return render(request, 'staff/create_report.html', {'patient': patient})


@login_required
def report_list(request, patient_id):
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    patient = get_object_or_404(PatientProfile, id=patient_id)
    reports = Report.objects.filter(generated_for=patient).order_by('-generated_at')

    return render(request, 'staff/report_list.html', {'reports': reports, 'patient': patient})


@login_required
def report_detail(request, report_id):
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    report = get_object_or_404(Report, id=report_id)
    return render(request, 'staff/report_detail.html', {'report': report})


@login_required
def download_report(request, report_id):
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    report = get_object_or_404(Report, id=report_id)

    # Prevent 500 Server Errors if the file was deleted from the hard drive
    if not report.file_path or not os.path.exists(report.file_path.path):
        raise Http404("The requested file is missing from the server.")

    response = FileResponse(open(report.file_path.path, 'rb'), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{report.title}.pdf"'
    return response


@login_required
def audit_log_list(request):
    # Strict Security: Only staff should see system audit logs
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    # Order by newest first (assuming your model uses 'timestamp' or 'created_at')
    # Change '-timestamp' to whatever your datetime field is named
    logs_list = AuditLog.objects.all().order_by('-timestamp')

    # Pagination: Prevent server crashes by only loading 50 logs at a time
    paginator = Paginator(logs_list, 50)
    page_number = request.GET.get('page')
    logs = paginator.get_page(page_number)

    return render(request, 'staff/audit_log_list.html', {'logs': logs})


@login_required
def audit_log_detail(request, log_id):
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    log = get_object_or_404(AuditLog, id=log_id)
    return render(request, 'staff/audit_log_detail.html', {'log': log})


@login_required
def health_and_safety_protocols(request):
    # Security: Ensure only staff can access internal SOPs
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    # Assuming you might want to order these by newest or a specific category
    protocols = HealthAndSafetyProtocol.objects.all().order_by('id')
    return render(request, 'staff/health_and_safety_protocols.html', {'protocols': protocols})


@login_required
def infection_control_practices(request):
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    practices = InfectionControlPractice.objects.all().order_by('id')
    return render(request, 'staff/infection_control_practices.html', {'practices': practices})


@login_required
def staff_list(request):
    # Security: Ensure only staff can view the internal directory
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    # select_related('user') prevents the N+1 query problem, making the page load much faster
    staff_members = Staff.objects.select_related('user').all().order_by('role', 'user__last_name')

    return render(request, 'staff/staff_list.html', {'staff': staff_members})


@login_required
def staff_certifications(request, staff_id):
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    staff_member = get_object_or_404(Staff.objects.select_related('user'), id=staff_id)
    # Order certifications so the most recently issued ones appear first
    certifications = staff_member.certifications.all().order_by('-issue_date')

    return render(request, 'staff/staff_certifications.html', {
        'staff_member': staff_member,
        'certifications': certifications
    })


@login_required
def notification_list(request):
    # Security: Ensure only staff can access this specific staff portal view
    if not hasattr(request.user, 'staff_profile'):
        return redirect('patients:home')

    # Fetch the 50 most recent notifications to prevent endless scrolling lag
    notifications = Notification.objects.filter(
        recipient=request.user
    ).order_by('-created_at')[:50]

    # Optional: Count unread notifications for a badge in the header
    unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()

    return render(request, 'staff/notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count
    })


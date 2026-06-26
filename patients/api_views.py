from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import status
from django.shortcuts import get_object_or_404

from staff.models import Assignment, Appointment, Notification
from .models import *
from .serializers import *
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.contrib.auth import authenticate, login
from rest_framework_simplejwt.tokens import AccessToken
import datetime

# API for Landing Page
@extend_schema(
    responses={
        200: inline_serializer(
            name='LandingResponse',
            fields={'message': serializers.CharField()}
        )
    },
    description="Public welcome endpoint for the Patients API."
)
@api_view(['GET'])
@permission_classes([AllowAny])
def api_landing(request):
    return Response({"message": "Welcome to the Patients API"})


# API for Register
@extend_schema(
    request=RegisterSerializer,
    responses={
        201: inline_serializer(
            name='RegisterSuccess',
            fields={'message': serializers.CharField()}
        )
    },
    description="Registers a new patient account in the hospital system."
)
@api_view(['POST'])
@permission_classes([AllowAny])
def api_register(request):
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response({"message": "User registered successfully"}, status=201)

    print("SERIALIZER ERRORS:", serializer.errors)

    return Response(serializer.errors, status=400)


# API for Login
@extend_schema(
    request=inline_serializer(
        name='LoginRequest',
        fields={
            'username': serializers.CharField(),
            'password': serializers.CharField(write_only=True),
        }
    ),
    responses={
        200: inline_serializer(
            name='LoginResponse',
            fields={
                'message': serializers.CharField(),
                'token': serializers.CharField(),
                'user_id': serializers.IntegerField(),
            }
        ),
        400: inline_serializer(
            name='LoginErrorResponse',
            fields={
                'error': serializers.CharField()
            }
        )
    },
    description="Authenticates a patient using their username and password, returning a JWT access token for session management."
)
@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(username=username, password=password)

    if user:
        # Log the user in (optional, for Django session-based auth)
        login(request, user)

        # Generate an access token for the authenticated user
        token = AccessToken.for_user(user)

        # Get the expiration timestamp
        expiration_timestamp = token['exp']

        # Convert to a readable datetime
        expiration_time = datetime.datetime.fromtimestamp(expiration_timestamp)

        print(f"Token expires at: {expiration_time}")

        # Save token to the log model
        patient = PatientProfile.objects.get(user=user)
        TokenLog.objects.create(patient=patient, token=str(token))

        return Response({
            "message": "Loogged in successfully",
            "token": str(token),
            "user_id": user.pk,
            "username": user.username,
        })

    return Response({"error": "Invalid credentials"}, status=400)


# API for Logout
@extend_schema(
    request=None,  # Tells Swagger UI not to expect a JSON body
    responses={
        200: inline_serializer(
            name='PatientLogoutResponse',
            fields={'message': serializers.CharField()}
        )
    },
    description="Logs out the authenticated patient and invalidates their current session."
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_logout(request):
    from django.contrib.auth import logout
    logout(request)
    return Response({"message": "Logged out successfully"})


# API for Profile
@extend_schema(
    responses={
        200: ProfileSerializer,
        404: inline_serializer(
            name='ProfileNotFoundError',
            fields={'error': serializers.CharField()}
        )
    },
    description="Retrieves the detailed profile information for the authenticated patient."
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_profile(request):
    try:
        patient = request.user.Patient  # Get the associated Patient instance
        profile = patient.profile  # Get the Profile linked to Patient
    except AttributeError:
        return Response({'error': 'Profile not found'}, status=404)

    serializer = ProfileSerializer(profile)
    return Response(serializer.data)


# API for Update Profile
@extend_schema(
    request=ProfileSerializer,
    responses={
        200: ProfileSerializer,
        400: inline_serializer(
            name='ProfileUpdateError',
            fields={'error': serializers.CharField()} # DRF validation errors
        ),
        404: inline_serializer(
            name='ProfileNotFound',
            fields={'detail': serializers.CharField()} # Standard get_object_or_404 response
        )
    },
    description="Updates the authenticated patient's profile. You only need to send the specific fields you wish to change."
)
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def api_update_profile(request):
    profile = get_object_or_404(PatientProfile, user=request.user.Patient)
    serializer = ProfileSerializer(profile, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=400)

# API for Medication Reminders
@extend_schema(
    responses={
        200: MedicationReminderSerializer(many=True)
    },
    description="Retrieves a list of all active medication reminders for the authenticated patient."
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_medication_reminders(request):
    reminders = MedicationReminder.objects.filter(patient=request.user.Patient)
    serializer = MedicationReminderSerializer(reminders, many=True)
    return Response(serializer.data)

# API for Feedback
@extend_schema(
    request=FeedbackSerializer,
    responses={
        200: inline_serializer(
            name='FeedbackSuccess',
            fields={'message': serializers.CharField()}
        )
    },
    description="Submits patient feedback to the hospital system."
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_feedback(request):
    serializer = FeedbackSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(patient=request.user.Patient)
        return Response({"message": "Feedback submitted successfully"})
    return Response(serializer.errors, status=400)

# API for Treatment Plans
@extend_schema(
    responses={
        200: TreatmentPlanSerializer(many=True)
    },
    description="Retrieves a list of all active treatment plans for the authenticated patient."
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_treatment_plans(request):
    plans = TreatmentPlan.objects.filter(patient=request.user.Patient)
    serializer = TreatmentPlanSerializer(plans, many=True)
    return Response(serializer.data)

# API for Emergency Contact
@extend_schema(
    methods=['GET'],
    responses={200: EmergencyServiceSerializer},
    description="Retrieves the emergency service record for the authenticated patient."
)
@extend_schema(
    methods=['POST'],
    request=EmergencyServiceSerializer,
    responses={
        200: inline_serializer(
            name='EmergencyServiceSuccess',
            fields={'message': serializers.CharField()}
        )
    },
    description="Submits a new emergency service request for the authenticated patient."
)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_emergency_contact(request):
    if request.method == 'GET':
        emergency_service = EmergencyService.objects.filter(patient=request.user.Patient).first()
        if emergency_service:
            serializer = EmergencyServiceSerializer(emergency_service)
            return Response(serializer.data)
        return Response({"message": "No emergency services found"})

    elif request.method == 'POST':
        data = request.data
        data['patient'] = request.user.Patient.id  # Link to logged-in patient
        serializer = EmergencyServiceSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Emergency service request submitted"})
        return Response(serializer.errors, status=400)


# --- INTERNAL AI BOT ENDPOINTS ---

@extend_schema(
    request=inline_serializer(
        name="BotEmergencyRequest",
        fields={
            "patient_id": serializers.IntegerField(),
            "location": serializers.CharField(),
            "emergency_type": serializers.CharField()
        }
    ),
    responses={
        201: inline_serializer(
            name="BotEmergencyResponse",
            fields={"status": serializers.CharField(), "message": serializers.CharField()}
        )
    },
    description="Internal endpoint for the AI Agent to dispatch an emergency service."
)
@api_view(['POST'])
@permission_classes([AllowAny])
def create_bot_emergency(request):
    data = request.data

    patient_id = data.get('patient_id')
    location = data.get('location')
    emergency_type = data.get('emergency_type')

    if not all([patient_id, location, emergency_type]):
        return Response({"error": "Missing required fields."}, status=400)

    try:
        patient = PatientProfile.objects.get(id=patient_id)

        # Create the emergency record linked to the patient
        emergency = EmergencyService.objects.create(
            patient=patient,
            location=location,
            emergency_type=emergency_type,
            status='Pending'  # Explicitly setting this so hospital ops can see it immediately
        )

        return Response({
            "status": "success",
            "message": f"Emergency recorded. ID: {emergency.id}"
        }, status=201)

    except PatientProfile.DoesNotExist:
        return Response({"error": "Patient not found."}, status=404)
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
def chatbot_my_doctors(request):
    """
    Returns only the doctors assigned to a specific patient,
    along with their schedule working hours.
    """
    username = request.query_params.get('username')
    day_of_week = request.query_params.get('day', '').lower()

    if not username:
        return Response({'error': 'Usesrname parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

    # 1. Look up the patient profile via the linked User username
    patient = get_object_or_404(PatientProfile, user__username=username)

    # 2. Get assignments for this patient
    assignments = Assignment.objects.filter(patient=patient).select_related('doctor', 'doctor__doctor_schedule')

    doctors_data = []
    for assign in assignments:
        doctor = assign.doctor
        doc_info = {
            "id": doctor.id,
            "name": doctor.user.get_full_name() or doctor.user.username,
            "username": doctor.user.username,
            "availability": "Not scheduled"
        }

        # 3. If they have a schedule and a specific day was requested, pull hours
        # 3. If they have a schedule and a specific day was requested, pull hours
        if hasattr(doctor, 'doctor_schedule') and day_of_week:
            schedule = doctor.doctor_schedule
            # Fetch the TimeBlocks for the requested day
            working_blocks = schedule.blocks.filter(day_of_week=day_of_week)

            if working_blocks.exists():
                # Format multiple shifts into a clean string for the AI to read
                time_strings = [f"{b.start_time.strftime('%I:%M %p')} to {b.end_time.strftime('%I:%M %p')}" for b in
                                working_blocks]
                doc_info["availability"] = f"Available from {' and '.join(time_strings)}"
            else:
                doc_info["availability"] = "Not available on thiis day"
        elif hasattr(doctor, 'doctor_schedule'):
            doc_info["availability"] = "Schedule exists (specify a day to check working hours)"

        doctors_data.append(doc_info)

    return Response({"assigned_doctors": doctors_data}, status=status.HTTP_200_OK)


@api_view(['POST'])
def verify_and_book(request):
    from datetime import datetime, timedelta
    """
    Verifies the patient's secret key and books the appointment.
    """
    patient_username = request.data.get('patient_username')
    doctor_target = request.data.get('doctor_name')  # e.g., "Dr. Smith"
    secret_key = request.data.get('secret_key')
    scheduled_time = request.data.get('scheduled_time')  # e.g., "2026-06-10T09:00"

    if not all([patient_username, doctor_target, secret_key, scheduled_time]):
        return Response({'error': 'Missing required booking information.'}, status=status.HTTP_400_BAD_REQUEST)

    clean_target = doctor_target.replace("Dr.", "").replace("Doctor", "").strip()
    doc_identifier = clean_target.split()[0] if clean_target else ""

    # 2. VERIFY THE SECRET KEY
    try:
        # Check if an assignment exists with this exact patient, doctor, and key
        assignment = Assignment.objects.get(
            patient__user__username=patient_username,
            doctor__user__username__icontains=doc_identifier,
            secret_key=secret_key
        )
    except Assignment.DoesNotExist:
        return Response({'error': 'Authentication failed. Invalid secret key.'}, status=status.HTTP_403_FORBIDDEN)
    print(f" Doctor's name is {doc_identifier}")

    # 3. CREATE THE APPOINTMENT
    try:
        # Parse the AI's string ("2026-06-10T10:00") into a Python datetime object
        parsed_datetime = datetime.strptime(scheduled_time, "%Y-%m-%dT%H:%M")
        req_date = parsed_datetime.date()
        req_time = parsed_datetime.time()
        req_day_str = req_date.strftime('%A').lower()  # Turns '2026-06-10' into 'wednesday'

        doctor_schedule = assignment.doctor.doctor_schedule

        # --- CHECKPOINT 1: Is the doctor working at this specific time? ---
        # Get all shifts (TimeBlocks) for this specific day
        # --- CHECKPOINT 1: Is the doctor working at this specific time? ---
        # --- CHECKPOINT 1: Is the doctor working at this specific time? ---
        working_blocks = doctor_schedule.blocks.filter(day_of_week=req_day_str)

        print(f"\n=== DEBUG: CHECKPOINT 1 ===")
        print(f"Requested Day: {req_day_str}")
        print(f"Total blocks found for this day: {working_blocks.count()}")

        if not working_blocks.exists():
            print(f"FAIL: Doctor is completely off on {req_day_str}")
            return Response(
                {'error': f'Dr. {doc_identifier} does not take appointments on {req_day_str.capitalize()}s.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # FIX 1: Calculate the exact time the requested appointment will END
        req_end_datetime = parsed_datetime + timedelta(minutes=doctor_schedule.appointment_duration)
        req_end_time = req_end_datetime.time()

        print(f"Requested Start Time: {req_time}")
        print(f"Appointment Duration: {doctor_schedule.appointment_duration} mins")
        print(f"Calculated End Time:  {req_end_time}")
        print(f"---------------------------")

        is_within_shift = False
        for block in working_blocks:
            print(f"Evaluating Block: {block.start_time} to {block.end_time}")

            start_is_valid = block.start_time <= req_time
            end_is_valid = req_end_time <= block.end_time

            print(f"  - Start check ({block.start_time} <= {req_time}): {start_is_valid}")
            print(f"  - End check   ({req_end_time} <= {block.end_time}): {end_is_valid}")

            # Now we check that BOTH the start time and the end time fit inside the doctor's shift
            if start_is_valid and end_is_valid:
                print("  -> SUCCESS! Time perfectly fits this block.")
                is_within_shift = True
                break
            else:
                print("  -> REJECTED: Time spills out of this block bounds.")

        if not is_within_shift:
            print("FAIL: The time didn't fit into ANY of the available blocks.")
            print("===========================\n")
            return Response(
                {
                    'error': 'The requested time falls outside the doctor\'s working shifts or spills over their closing time.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        print("PASS: Checkpoint 1 Cleared!")
        print("===========================\n")

        # --- CHECKPOINT 2: Does it overlap with another patient? ---
        # Calculate total time taken by one appointment + buffer
        total_minutes = doctor_schedule.appointment_duration + doctor_schedule.buffer_time

        # FIX 2: We subtract 1 minute so perfectly back-to-back appointments don't clash
        danger_delta = timedelta(minutes=total_minutes - 1)

        # Calculate the "Danger Zone"
        start_bound = (parsed_datetime - danger_delta).time()
        end_bound = (parsed_datetime + danger_delta).time()

        clashing_appointments = Appointment.objects.filter(
            doctor=assignment.doctor,
            date=req_date,
            time__range=(start_bound, end_bound),
            status__in=['Scheduled', 'Pending']  # Ignore 'Cancelled' or 'Completed'
        )

        if clashing_appointments.exists():
            return Response(
                {
                    'error': 'This time slot is too close to an existing appointment. Please ask the bot for another time.'},
                status=status.HTTP_409_CONFLICT
            )

        # --- CHECKPOINT CLEARED: Create the Pending Request ---
        appointment = Appointment.objects.create(
            patient=assignment.patient,
            doctor=assignment.doctor,
            date=req_date,
            time=req_time,
            reason="Chatbot Scheduled Appointment",
            status="Pending",  # Changed from "Scheduled" to "Pending"
            is_confirmed=False  # Awaiting Doctor's approval
        )

    except ValueError:
        return Response({'error': 'Invalid date/time format received from bot.'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({'error': f'Failed to create appointment: {str(e)}'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # 4. TRIGGER AUTOMATED NOTIFICATION ... (Your existing notification code goes here)

    try:
        # Fallback to username if they haven't set their first/last name
        patient_display_name = assignment.patient.user.get_full_name() or assignment.patient.user.username

        # Make the time look pretty for the notification (e.g., "Jun 10 at 09:00 AM")
        pretty_time = parsed_datetime.strftime("%b %d at %I:%M %p")

        notification_msg = f"New appointment scheduled by {patient_display_name} for {pretty_time}."

        # Create the notification linked to the doctor's underlying User account
        Notification.objects.create(
            message=notification_msg,
            recipient=assignment.doctor.user,  # MUST be the .user object, not the Staff object
            notification_type='appointment',
            is_urgent=False
        )
    except Exception as e:
        # We don't want a failed notification to ruin a successful booking, so just print/log it
        print(f"Notification failed to send: {e}")

    # Optional: Mark key as verified if you want to track usage
    if not assignment.is_key_verified:
        assignment.is_key_verified = True
        assignment.save()

    return Response({
        'message': 'Appointment request successfully submitted to the doctor for review!',
        'appointment_id': appointment.id
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
def chatbot_my_appointments(request):
    """
    Returns all appointments for a specific patient to the chatbot.
    """
    username = request.query_params.get('username')

    if not username:
        return Response({'error': 'Username parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

    # Fetch appointments linked to this user, ordered by date
    appointments = Appointment.objects.filter(patient__user__username=username).order_by('date', 'time')

    if not appointments.exists():
        return Response({"appointments": "No appointments found for this patient."})

    appointments_data = []
    for appt in appointments:
        doc_name = appt.doctor.user.get_full_name() or appt.doctor.user.username
        appointments_data.append({
            "doctor": f"Dr. {doc_name.capitalize()}",
            "date": appt.date.strftime("%A, %B %d, %Y"),
            "time": appt.time.strftime("%I:%M %p"),
            "status": appt.status,
            "is_confirmed": appt.is_confirmed
        })

    return Response({"appointments": appointments_data}, status=status.HTTP_200_OK)
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from django.shortcuts import get_object_or_404
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
        TokenLog.objects.create(user=patient, token=str(token))

        return Response({
            "message": "Logged in successfully",
            "token": str(token),  # Return the token as a string
            "user_id": user.pk  # Include user ID or any other user info as needed
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
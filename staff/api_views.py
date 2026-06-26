# views.py (API views)
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework.permissions import IsAuthenticated
from .models import *
from .serializer import *
from .permissions import *
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from .utils import generate_report_pdf
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import NotFound
from patients.models import PatientProfile
from django.contrib.auth import login, logout
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.authtoken.views import ObtainAuthToken
from datetime import date, timedelta, datetime
from django.shortcuts import get_object_or_404
from rest_framework.status import HTTP_403_FORBIDDEN
from rest_framework import viewsets, permissions, generics
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.viewsets import ViewSet
import jwt
import datetime
from rest_framework_simplejwt.tokens import AccessToken

# Define the permission classes
class StaffPermission(IsAuthenticated):
    def has_permission(self, request, view):
        return hasattr(request.user, 'staff')


# adjust the apis to work properly, especially the staff p
class DoctorPermission(IsDoctor):
    def has_permission(self, request, view):
        # Ensure user is a doctor by checking role
        return hasattr(request.user, 'staff') and request.user.staff.role == 'doctor'


# Staff viewset to manage staff through the API
class StaffViewSet(viewsets.ModelViewSet):
    queryset = Staff.objects.all()
    serializer_class = StaffSerializer
    permission_classes = [StaffPermission]  # Only staff can access this


@extend_schema(
    request=None,  # Tells Swagger UI not to draw a text box for JSON input
    responses={
        200: inline_serializer(
            name='StaffLogoutResponse',
            fields={'message': serializers.CharField()}
        )
    },
    description="Logs out the authenticated staff member and invalidates their current session."
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def staff_logout(request):
    logout(request)
    return Response({'message': 'Logged out successfully.'}, status=status.HTTP_200_OK)


class RegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses={
            200: inline_serializer(
                name='StaffRegisterInstruction',
                fields={'message': serializers.CharField()}
            )
        },
        description="Provides instructions for registering a new staff account."
    )
    def get(self, request):
        return Response({"message": "Send a POST request with user registration details."}, status=status.HTTP_200_OK)

    @extend_schema(
        request=StaffRegisterSerializer,
        responses={
            201: inline_serializer(
                name='StaffRegisterSuccess',
                fields={'message': serializers.CharField()}
            )
        },
        description="Registers a new staff member (Admin or Doctor) into the hospital system."
    )
    def post(self, request):
        print('data sent')
        serializer = StaffRegisterSerializer(data=request.data)
        if serializer.is_valid():
            staff = serializer.save()
            return Response({'message': 'Registration successful!'}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# class LoginView(APIView):
#     def post(self, request):
#         username = request.data.get('username')
#         password = request.data.get('password')
#
#         user = authenticate(request, username=username, password=password)
#         if user is not None:
#             login(request, user)
#             return Response({'message': 'Login successful!'}, status=status.HTTP_200_OK)
#         return Response({'error': 'Invalid credentials'}, status=status.HTTP_400_BAD_REQUEST)


class LoginView(ObtainAuthToken):
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token = AccessToken.for_user(user)  # Generate a valid AccessToken
        # Get the expiration timestamp
        expiration_timestamp = token['exp']

        # Convert to a readable datetime
        expiration_time = datetime.datetime.fromtimestamp(expiration_timestamp)

        print(f"Token expires at: {expiration_time}")
        return Response({'token': str(token), 'user_id': user.pk})


class StaffDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsStaffMember]

    @extend_schema(
        responses={
            200: inline_serializer(
                name='StaffDashboardResponse',
                fields={'message': serializers.CharField()}
            )
        },
        description="Retrieves a personalized welcome message for the authenticated staff member based on their RBAC role."
    )
    def get(self, request):
        print('gotten')  # This line will now be executed
        # No need to check role again, IsStaffMember already handles it
        return Response({'message': f"Welcome to the {request.user.staff_profile.role} dashboard!"}, status=200)


class TestView(APIView):
    @extend_schema(
        responses={
            200: inline_serializer(
                name='TestViewResponse',
                fields={'message': serializers.CharField()}
            )
        },
        description="A simple test endpoint to verify API routing and functionality."
    )
    def get(self, request):
        print("TestView: get() method called")
        return Response({'message': 'Test View'})


# Doctor viewset (access restricted to doctors)
class DoctorViewSet(viewsets.ModelViewSet):
    queryset = Staff.objects.filter(role='doctor')
    serializer_class = StaffSerializer
    permission_classes = [DoctorPermission]  # Only doctors can access this


class DoctorScheduleViewSet(viewsets.ModelViewSet):
    serializer_class = DoctorScheduleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if hasattr(self.request.user, 'staff_profile') and self.request.user.staff_profile.role == 'doctor':
            return DoctorSchedule.objects.filter(doctor=self.request.user.staff_profile)
        return DoctorSchedule.objects.none()

    def create(self, request, *args, **kwargs):
        # Restrict creation to only authenticated doctors
        if not hasattr(request.user, 'staff_profile') or request.user.staff_profile.role != 'doctor':
            return Response({'error': 'Unauthorized access.'}, status=status.HTTP_403_FORBIDDEN)

        return super().create(request, *args, **kwargs)


class AppointmentViewSet(viewsets.ModelViewSet):
    queryset = Appointment.objects.all()
    serializer_class = StaffAppointmentSerializer

    def create(self, request, *args, **kwargs):
        patient_id = request.data.get('patient')
        doctor_id = request.data.get('doctor')
        reason = request.data.get('reason')
        scheduled_time = request.data.get('scheduled_time')

        # Validate inputs
        if not all([patient_id, doctor_id, scheduled_time]):
            return Response({'error': 'Patient, doctor, and scheduled time are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            scheduled_time = datetime.strptime(scheduled_time, '%Y-%m-%dT%H:%M')
        except ValueError:
            return Response({'error': 'Invalid date/time format. Use YYYY-MM-DDTHH:MM.'}, status=status.HTTP_400_BAD_REQUEST)

        day_of_week = scheduled_time.strftime('%A').lower()

        # Check if the doctor exists and has a schedule
        try:
            doctor = Staff.objects.get(id=doctor_id, role='doctor')
        except Staff.DoesNotExist:
            return Response({'error': 'Invalid doctor ID or doctor not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not hasattr(doctor, 'doctor_schedule'):
            return Response({'error': 'Doctor does not have a schedule.'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate the doctor's availability
        schedule = doctor.doctor_schedule
        start_time = getattr(schedule, f"{day_of_week}_start", None)
        end_time = getattr(schedule, f"{day_of_week}_end", None)

        if not start_time or not end_time:
            return Response({'error': f"Doctor is not available on {day_of_week.capitalize()}."}, status=status.HTTP_400_BAD_REQUEST)

        if not (start_time <= scheduled_time.time() <= end_time):
            return Response({'error': 'Scheduled time is outside the doctor\'s working hours.'}, status=status.HTTP_400_BAD_REQUEST)

        # Check for conflicting appointments
        conflicting_appointments = Appointment.objects.filter(
            doctor=doctor,
            scheduled_time__gte=scheduled_time,
            scheduled_time__lt=scheduled_time + timedelta(minutes=30)
        )
        if conflicting_appointments.exists():
            return Response({'error': 'The doctor already has an appointment at the requested time.'}, status=status.HTTP_400_BAD_REQUEST)

        # Create the appointment
        patient = get_object_or_404(PatientProfile, id=patient_id)
        appointment = Appointment.objects.create(
            patient=patient,
            doctor=doctor,
            scheduled_time=scheduled_time,
            reason=reason,
            status='scheduled',
        )

        serializer = self.get_serializer(appointment)
        return Response(serializer.data, status=status.HTTP_201_CREATED)



class VitalSignViewSet(viewsets.ModelViewSet):
    queryset = VitalSign.objects.all()
    serializer_class = VitalSignSerializer

    def perform_create(self, serializer):
        patient_id = self.request.data.get('patient_id')
        patient = get_object_or_404(PatientProfile, id=patient_id)
        serializer.save(patient=patient)



class CarePlanPermission(permissions.BasePermission):
    """
    Permission to check if user is authenticated and has permission to create care plans.
    """
    def has_permission(self, request, view):
        if request.user.is_authenticated:
            return True
        return False

class CarePlanViewSet(viewsets.ModelViewSet):
    queryset = CarePlan.objects.all()
    serializer_class = CarePlanSerializer
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [CarePlanPermission]

    def create(self, request, *args, **kwargs):
        """
        Override create method to handle data from request body.
        """
        data = request.data
        patient = PatientProfile.objects.get(pk=data['patient'])
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save(patient=patient, doctor=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class MedicalRecordPermission(permissions.BasePermission):
    """
    Permission to check if user is authenticated and has permission to create medical records.
    """
    def has_permission(self, request, view):
        if request.user.is_authenticated:
            return True
        return False

class MedicalRecordViewSet(viewsets.ModelViewSet):
    queryset = MedicalRecord.objects.all()
    serializer_class = StaffMedicalRecordSerializer
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [MedicalRecordPermission]

    def create(self, request, *args, **kwargs):
        """
        Override create method to handle data from request body.
        """
        data = request.data
        patient = PatientProfile.objects.get(pk=data['patient'])
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save(patient=patient)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class LabTestPermission(permissions.BasePermission):
    """
    Permission to check if user is authenticated and has permission to create lab tests.
    """
    def has_permission(self, request, view):
        if request.user.is_authenticated:
            return True
        return False

class LabTestViewSet(viewsets.ModelViewSet):
    queryset = LabTest.objects.all()
    serializer_class = LabTestSerializer
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [LabTestPermission]

    def create(self, request, *args, **kwargs):
        """
        Override create method to handle data from request body.
        """
        data = request.data
        patient = PatientProfile.objects.get(pk=data['patient'])
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save(patient=patient, ordered_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PrescriptionPermission(permissions.BasePermission):
    """
    Permission to check if user is authenticated and has permission to create prescriptions.
    """
    def has_permission(self, request, view):
        if request.user.is_authenticated:
            return True
        return False

class PrescriptionViewSet(viewsets.ModelViewSet):
    queryset = Prescription.objects.all()
    serializer_class = StaffPrescriptionSerializer
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [PrescriptionPermission]

    def create(self, request, *args, **kwargs):
        """
        Override create method to handle data from request body.
        """
        data = request.data
        patient = PatientProfile.objects.get(pk=data['patient'])
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save(patient=patient, doctor=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class StaffMessageList(APIView):
    def get(self, request):
        messages = StaffMessage.objects.all()
        serializer = StaffMessageSerializer(messages, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = StaffMessageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Send a message (POST request with sender and recipient data)
class SendStaffMessage(generics.CreateAPIView):
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        recipient_id = request.data.get('recipient_id')
        message_content = request.data.get('message_content')

        if recipient_id and message_content:
            try:
                recipient = Staff.objects.get(id=recipient_id)
                sender = Staff.objects.get(user=request.user)  # Assuming user is always a Staff instance

                message = StaffMessage(sender=sender, recipient=recipient, message_content=message_content)
                message.save()

                return Response({'message': f"Message sent to {recipient.user.username} successfully."}, status=status.HTTP_201_CREATED)

            except Staff.DoesNotExist:
                return Response({'error': "Recipient not found."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'error': "Please fill in all fields."}, status=status.HTTP_400_BAD_REQUEST)


class StaffInboxView(generics.ListAPIView):
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated & StaffPermission]  # Custom permission class for staff users

    def get_queryset(self):
        current_staff = Staff.objects.get(user=self.request.user)
        return StaffMessage.objects.filter(recipient=current_staff).order_by('-sent_at')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = StaffMessageSerializer(queryset, many=True)
        for message in queryset:
            message.is_read = True  # Mark all retrieved messages as read
            message.save()
        return Response(serializer.data)

class StaffMessageDetailView(generics.RetrieveAPIView):
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated & StaffPermission]  # Custom permission class for staff users

    serializer_class = StaffMessageSerializer

    def get_queryset(self):
        current_staff = Staff.objects.get(user=self.request.user)
        return StaffMessage.objects.filter(recipient=current_staff)

    def retrieve(self, request, message_id, *args, **kwargs):
        try:
            message = self.get_queryset().get(pk=message_id)
            if not message.is_read:
                message.is_read = True
                message.read_at = datetime.datetime.now()
                message.save()
            serializer = self.get_serializer(message)
            return Response(serializer.data)
        except StaffMessage.DoesNotExist:
            return Response({'error': 'Message not found or you do not have permission to view it.'}, status=status.HTTP_404_NOT_FOUND)


class DoctorPatientMessageList(ViewSet):
    serializer_class = DoctorPatientMessageSerializer
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def list(self, request, patient_id=None):
        if not User.objects.filter(id=patient_id).exists():
            return Response({'error': 'Patient not found'}, status=status.HTTP_404_NOT_FOUND)
        messages = DoctorPatientMessage.objects.filter(patient_id=patient_id)
        serializer = DoctorPatientMessageSerializer(messages, many=True)
        return Response(serializer.data)

    def create(self, request, patient_id=None):
        if not User.objects.filter(id=patient_id).exists():
            return Response({'error': 'Patient not found'}, status=status.HTTP_404_NOT_FOUND)
        if not request.user.staff_profile.role == 'doctor':
            return Response({'error': 'Permission denied. Only doctors can send messages.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = DoctorPatientMessageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(patient_id=patient_id, sender=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class DoctorPatientMessageDetail(generics.RetrieveAPIView):
    authentication_classes = [SessionAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated]  # Assuming permission for doctors or patients

    serializer_class = DoctorPatientMessageSerializer

    def get_queryset(self):
        message_id = self.kwargs['pk']
        return DoctorPatientMessage.objects.filter(pk=message_id)

    def get_object(self):
        queryset = self.get_queryset()
        if not queryset.exists():
            return Response({'error': 'Message not found'}, status=status.HTTP_404_NOT_FOUND)
        return queryset.get()


class TeamMessageList(APIView):
    def get(self, request, patient_id):
        messages = TeamMessage.objects.filter(patient_id=patient_id)
        serializer = TeamMessageSerializer(messages, many=True)
        return Response(serializer.data)

    def post(self, request, patient_id):
        serializer = TeamMessageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(patient_id=patient_id)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class InsuranceViewSet(viewsets.ModelViewSet):
    queryset = Insurance.objects.all()
    serializer_class = InsuranceSerializer


class BillViewSet(viewsets.ModelViewSet):
    queryset = Bill.objects.all()
    serializer_class = BillSerializer


class InsuranceClaimViewSet(viewsets.ModelViewSet):
    queryset = InsuranceClaim.objects.all()
    serializer_class = InsuranceClaimSerializer


class EmergencyAlertCreateView(APIView):
    def post(self, request, format=None):
        serializer = EmergencyAlertSerializer(data=request.data)
        if serializer.is_valid():
            alert = serializer.save()
            return Response(EmergencyAlertSerializer(alert).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EmergencyAlertListView(ListAPIView):
    queryset = EmergencyAlert.objects.all()
    serializer_class = EmergencyAlertSerializer


class EmergencyAlertUpdateView(APIView):
    @extend_schema(
        request=EmergencyAlertSerializer,
        responses={200: EmergencyAlertSerializer},
        description="Partially updates an emergency alert (e.g., marking it as resolved or adding notes)."
    )
    def patch(self, request, pk, format=None):
        alert = EmergencyAlert.objects.get(pk=pk)
        serializer = EmergencyAlertSerializer(alert, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MedicalSupplyViewSet(viewsets.ModelViewSet):
    queryset = MedicalSupply.objects.all()
    serializer_class = MedicalSupplySerializer


class StockAlertViewSet(viewsets.ModelViewSet):
    queryset = StockAlert.objects.filter(alert_status='unresolved')
    serializer_class = StockAlertSerializer

    def perform_create(self, serializer):
        supply = serializer.validated_data['supply']
        if supply.is_below_reorder_level():
            alert_message = f"Stock for {supply.name} is below the reorder level."
            serializer.save(alert_message=alert_message)


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer


class HospitalPerformanceMetricsViewSet(viewsets.ModelViewSet):
    queryset = HospitalPerformanceMetrics.objects.all()
    serializer_class = HospitalPerformanceMetricsSerializer


class ResourceAllocationViewSet(viewsets.ModelViewSet):
    queryset = ResourceAllocation.objects.all()
    serializer_class = ResourceAllocationSerializer


class PerformanceAnalyticsViewSet(viewsets.ModelViewSet):
    queryset = PerformanceAnalytics.objects.all()
    serializer_class = PerformanceAnalyticsSerializer


class ReportViewSet(viewsets.ModelViewSet):
    queryset = Report.objects.all()
    serializer_class = ReportSerializer

    def perform_create(self, serializer):
        report = serializer.save(generated_by=self.request.user)
        file_path = generate_report_pdf(report)  # Utility function to generate PDF
        report.file_path = file_path
        report.save()


class AuditLogViewSet(viewsets.ModelViewSet):
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    http_method_names = ['get']



class HealthAndSafetyProtocolViewSet(viewsets.ModelViewSet):
    queryset = HealthAndSafetyProtocol.objects.all()
    serializer_class = HealthAndSafetyProtocolSerializer


class InfectionControlPracticeViewSet(viewsets.ModelViewSet):
    queryset = InfectionControlPractice.objects.all()
    serializer_class = InfectionControlPracticeSerializer


class CertificationViewSet(viewsets.ModelViewSet):
    queryset = Certification.objects.all()
    serializer_class = CertificationSerializer


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)  # Get notifications for the logged-in user


# ViewSet for handling patients
class PatientViewSet(viewsets.ViewSet):
    serializer_class = PatientSerializer
    queryset = PatientProfile.objects.all()

    # Search patients by username or email
    @action(detail=False, methods=['get'])
    def search_patient(self, request):
        query = request.query_params.get('q', '')
        if query:
            patients = PatientProfile.objects.filter(user__username__icontains=query) | PatientProfile.objects.filter(
                user__email__icontains=query)
        else:
            patients = PatientProfile.objects.all()

        serializer = PatientSerializer(patients, many=True)
        return Response(serializer.data)

    # Display details of a specific patient
    @action(detail=True, methods=['get'])
    def display_patient(self, request, pk=None):
        try:
            patient = PatientProfile.objects.get(id=pk)
        except PatientProfile.DoesNotExist:
            raise NotFound("Patient not found")

        serializer = PatientSerializer(patient)
        return Response(serializer.data)


# --- INTERNAL AI BOT ENDPOINTS ---

@extend_schema(
    responses={200: inline_serializer(name='BotScheduleResponse',
                                      fields={'start': serializers.CharField(), 'end': serializers.CharField()})},
    description="Internal endpoint for the FastAPI AI Agent to check doctor availability."
)
@api_view(['GET'])
@permission_classes([AllowAny])
def get_bot_schedule(request):
    doctor_name = request.GET.get('doctor', '').strip()
    day = request.GET.get('day', '').lower().strip()

    try:
        # Find the doctor by matching part of their username or last name
        staff_member = Staff.objects.filter(user__username__icontains=doctor_name, role='doctor').first()
        if not staff_member:
            return Response({"error": "Doctor not found"}, status=404)

        schedule = DoctorSchedule.objects.get(doctor=staff_member)

        # Dynamically grab the start and end times for the requested day
        start_time = getattr(schedule, f"{day}_start", None)
        end_time = getattr(schedule, f"{day}_end", None)

        if not start_time or not end_time:
            return Response({"error": "Not scheduled"}, status=404)

        return Response({
            "start": start_time.strftime("%H:%M"),
            "end": end_time.strftime("%H:%M")
        }, status=200)

    except DoctorSchedule.DoesNotExist:
        return Response({"error": "Schedule not found"}, status=404)


# --- INTERNAL AI BOT ENDPOINTS (Continuing from the schedule endpoint) ---

@extend_schema(
    responses={
        200: inline_serializer(
            name='BotLabResultResponse',
            fields={'patient_name': serializers.CharField(), 'test_name': serializers.CharField(),
                    'status': serializers.CharField(), 'findings': serializers.CharField()}
        )
    },
    description="Internal endpoint for the AI Agent to fetch a patient's most recent lab results."
)
@api_view(['GET'])
@permission_classes([AllowAny])  # The firewall/network configuration secures this, not user auth
def get_bot_lab_results(request):
    patient_id = request.GET.get('patient_id')

    if not patient_id:
        return Response({"error": "patient_id is required"}, status=400)

    try:
        # Fetch the patient
        patient = PatientProfile.objects.get(id=patient_id)

        # Get their most recent lab test that has a result
        recent_test = LabTest.objects.filter(patient=patient).order_by('-test_date').first()

        if not recent_test:
            return Response({"status": "No lab tests found for this patient."}, status=200)

        # Check if the result exists (since LabResult is OneToOne)
        if hasattr(recent_test, 'result'):
            return Response({
                "patient_name": patient.user.username,
                "test_name": recent_test.test_name,
                "status": recent_test.status,
                "findings": recent_test.result.findings,
                "date": recent_test.test_date.strftime("%Y-%m-%d")
            }, status=200)
        else:
            return Response({
                "patient_name": patient.user.username,
                "test_name": recent_test.test_name,
                "status": "Pending Result (Not yet uploaded)",
                "date": recent_test.test_date.strftime("%Y-%m-%d")
            }, status=200)

    except PatientProfile.DoesNotExist:
        return Response({"error": "Patient not found"}, status=404)


@extend_schema(
    responses={
        200: inline_serializer(
            name='BotInventoryResponse',
            fields={'name': serializers.CharField(), 'quantity': serializers.IntegerField(),
                    'status': serializers.CharField()}
        )
    },
    description="Internal endpoint for the AI Agent to check medical supply inventory."
)
@api_view(['GET'])
@permission_classes([AllowAny])
def get_bot_inventory(request):
    item_name = request.GET.get('item', '').strip()

    if not item_name:
        return Response({"error": "Item name is required"}, status=400)

    try:
        # Search for the item (case-insensitive partial match)
        supply = MedicalSupply.objects.filter(name__icontains=item_name).first()

        if not supply:
            return Response({"error": f"Item '{item_name}' not found in inventory directory."}, status=404)

        status_msg = "Critical - Below Reorder Level" if supply.is_below_reorder_level() else "Adequate Stock"

        return Response({
            "name": supply.name,
            "quantity": supply.quantity_in_stock,
            "reorder_level": supply.reorder_level,
            "status": status_msg
        }, status=200)

    except Exception as e:
        return Response({"error": str(e)}, status=500)


@extend_schema(
    request=inline_serializer(
        name="BotNotificationRequest",
        fields={
            "recipient_username": serializers.CharField(),
            "message": serializers.CharField(),
            "notification_type": serializers.CharField(),
            "is_urgent": serializers.BooleanField()
        }
    ),
    responses={
        201: inline_serializer(
            name="BotNotificationResponse",
            fields={"status": serializers.CharField(), "message": serializers.CharField()}
        )
    },
    description="Internal endpoint for the AI Agent to push a notification to a user."
)
@api_view(['POST'])
@permission_classes([AllowAny]) # Secure this with a custom API key or token signature if needed in production
def create_bot_notification(request):
    """
    Receives username strings from FastAPI and translates them to
    database relationships to create system alerts.
    """
    data = request.data

    username = data.get('recipient_username')
    message = data.get('message')
    notification_type = data.get('notification_type', 'appointment')  # Default fallback
    is_urgent = data.get('is_urgent', False)

    if not all([username, message]):
        return Response({"error": "Recipient username and message are required."}, status=400)

    try:
        # Find the target user (works for both Staff and Patients, case-insensitive)
        user = User.objects.get(username__iexact=username)

        # Create the notification
        notification = Notification.objects.create(
            recipient=user,
            message=message,
            notification_type=notification_type,
            is_urgent=is_urgent
        )

        return Response({
            "status": "success",
            "message": f"Notification successfully sent to {user.username}.",
            "notification_id": notification.id
        }, status=201)

    except User.DoesNotExist:
        return Response({"error": f"User '{username}' not found in the system."}, status=404)
    except Exception as e:
        return Response({"error": f"Internal database failure: {str(e)}"}, status=500)


@extend_schema(
    responses={200: inline_serializer(name='BotMetricsResponse', fields={})},
    description="Internal endpoint to fetch the latest hospital metrics."
)
@api_view(['GET'])
@permission_classes([AllowAny])
def get_bot_metrics(request):
    try:
        # Grab the absolute newest metrics record
        metrics = HospitalPerformanceMetrics.objects.order_by('-updated_at').first()
        if not metrics:
            return Response({"status": "No metrics available in the database."}, status=200)

        return Response({
            "bed_occupancy": metrics.bed_occupancy,
            "staff_available": metrics.staff_available,
            "patient_flow": metrics.patient_flow,
            "updated_at": metrics.updated_at.strftime("%Y-%m-%d %H:%M")
        }, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@extend_schema(
    responses={200: inline_serializer(name='BotCertsResponse', fields={})},
    description="Internal endpoint to fetch expiring staff certifications."
)
@api_view(['GET'])
@permission_classes([AllowAny])
def get_bot_expiring_certs(request):
    # Default to 30 days if the AI doesn't specify
    days = int(request.GET.get('days', 30))
    threshold_date = date.today() + timedelta(days=days)

    try:
        expiring_certs = Certification.objects.filter(
            is_valid=True,
            expiration_date__lte=threshold_date
        ).select_related('staff__user')

        if not expiring_certs.exists():
            return Response({"status": f"No certifications expiring within the next {days} days."}, status=200)

        results = []
        for cert in expiring_certs:
            staff_name = f"{cert.staff.user.first_name} {cert.staff.user.last_name}".strip() or cert.staff.user.username
            results.append({
                "staff_name": staff_name,
                "certification": cert.name,
                "expires_on": cert.expiration_date.strftime("%Y-%m-%d")
            })

        return Response({"expiring_certifications": results}, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])  # Requires an active session token (JWT) from the doctor/staff
def respond_to_appointment(request, appointment_id):
    """
    Allows a doctor to confirm or postpone a pending chatbot appointment request.
    """
    try:
        appointment = Appointment.objects.get(id=appointment_id)
    except Appointment.DoesNotExist:
        return Response({'error': 'Appointment request not found.'}, status=status.HTTP_404_NOT_FOUND)

    # Security check: Ensure the logged-in user is actually the doctor assigned to the record
    if request.user != appointment.doctor.user:
        return Response({'error': 'Unauthorized. You are not the assigned physician for this request.'},
                        status=status.HTTP_403_FORBIDDEN)

    action = request.data.get('action')  # Expected: 'confirm' or 'postpone'

    # --- SCENARIO A: DOCTOR CONFIRMS ---
    if action == 'confirm':
        appointment.is_confirmed = True
        appointment.status = 'Scheduled'
        appointment.save()

        # Generate a clean display name for the notification
        doc_name = appointment.doctor.user.get_full_name() or appointment.doctor.user.username
        pretty_time = f"{appointment.date.strftime('%B %d')} at {appointment.time.strftime('%I:%M %p')}"

        # Fire a success notification directly back to the patient's User account
        Notification.objects.create(
            message=f"Great news! Dr. {doc_name} has confirmed your appointment request for {pretty_time}.",
            recipient=appointment.patient.user,
            notification_type='appointment',
            is_urgent=False
        )

        return Response({'message': 'Appointment successfully locked in and scheduled.'}, status=status.HTTP_200_OK)

    # --- SCENARIO B: DOCTOR POSTPONES (COUNTER-OFFER) ---
    elif action == 'postpone':
        new_date_str = request.data.get('new_date')  # Expected: 'YYYY-MM-DD'
        new_time_str = request.data.get('new_time')  # Expected: 'HH:MM'

        if not new_date_str or not new_time_str:
            return Response({'error': 'Missing new date or time configurations for postponement.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            # Parse incoming text values into native date/time variables
            parsed_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
            parsed_time = datetime.strptime(new_time_str, "%H:%M").time()
        except ValueError:
            return Response({'error': 'Invalid date or time format strings supplied.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Update the appointment to the new proposed timeslot
        appointment.date = parsed_date
        appointment.time = parsed_time
        appointment.status = 'Rescheduled'
        appointment.is_confirmed = False  # Stays unconfirmed until the system/patient acknowledges it
        appointment.save()

        # Format a user-friendly string for the patient alert
        doc_name = appointment.doctor.user.get_full_name() or appointment.doctor.user.username
        pretty_new_time = f"{parsed_date.strftime('%B %d')} at {parsed_time.strftime('%I:%M %p')}"

        # Alert the patient that the doctor shifted the calendar slot
        Notification.objects.create(
            message=f"Dr. {doc_name} needed to reschedule. They have proposed a new slot: {pretty_new_time}.",
            recipient=appointment.patient.user,
            notification_type='appointment',
            is_urgent=False
        )

        return Response({'message': 'Appointment postponed successfully. Notification dispatched to patient.'},
                        status=status.HTTP_200_OK)

    else:
        return Response({'error': 'Invalid action parameter. Use "confirm" or "postpone".'},
                        status=status.HTTP_400_BAD_REQUEST)
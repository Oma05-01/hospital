# views.py (API views)
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
from datetime import timedelta, datetime
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


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def staff_logout(request):
    logout(request)
    return Response({'message': 'Logged out successfully.'}, status=status.HTTP_200_OK)


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"message": "Send a POST request with user registration details."}, status=status.HTTP_200_OK)

    def post(self, request):
        print('data sent')
        serializer = RegisterSerializer(data=request.data)
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

    def get(self, request):
        print('gotten')  # This line will now be executed
        # No need to check role again, IsStaffMember already handles it
        return Response({'message': f"Welcome to the {request.user.staff_profile.role} dashboard!"}, status=200)


class TestView(APIView):
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
    serializer_class = AppointmentSerializer

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
    serializer_class = MedicalRecordSerializer
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
    serializer_class = PrescriptionSerializer
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

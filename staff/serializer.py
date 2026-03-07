# serializers.py
from rest_framework import serializers
from .models import *
from patients.models import PatientProfile
from django.contrib.auth import authenticate


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']


class StaffSerializer(serializers.ModelSerializer):
    user = UserSerializer()  # Use a nested serializer for the User model

    class Meta:
        model = Staff
        fields = ['id', 'user', 'role', 'phone_number']  # Include fields relevant to Staff

    def create(self, validated_data):
        user_data = validated_data.pop('user')
        user = User.objects.create(**user_data)
        staff = Staff.objects.create(user=user, **validated_data)
        return staff


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    role = serializers.ChoiceField(choices=Staff.ROLE_CHOICES, required=False)
    specialty = serializers.CharField(required=False)
    phone_number = serializers.CharField(required=False)
    profile_picture = serializers.ImageField(required=False)

    def create(self, validated_data):
        # Create the user
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password']
        )
        # Create and return a Staff instance tied to the user
        staff = Staff.objects.create(user=user,
                                     role=validated_data.get('role'),
                                     specialty=validated_data.get('specialty'),
                                     phone_number=validated_data.get('phone_number'),
                                     profile_picture=validated_data.get('profile_picture'))
        return staff


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(username=data['username'], password=data['password'])
        if not user:
            raise ValidationError('Invalid username or password.')
        data['user'] = user
        return data


class DoctorScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorSchedule
        fields = [
            'id', 'doctor', 'monday_start', 'monday_end',
            'tuesday_start', 'tuesday_end', 'wednesday_start', 'wednesday_end',
            'thursday_start', 'thursday_end', 'friday_start', 'friday_end',
            'saturday_start', 'saturday_end', 'sunday_start', 'sunday_end'
        ]


class AppointmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = ['id', 'patient', 'doctor', 'scheduled_time', 'reason', 'status']


# serializers.py
class VitalSignSerializer(serializers.ModelSerializer):
    class Meta:
        model = VitalSign
        fields = ['id', 'patient', 'recorded_at', 'blood_pressure', 'temperature', 'pulse', 'weight', 'oxygen_saturation']


class CarePlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarePlan
        fields = ['id', 'patient', 'created_by', 'diagnosis', 'treatment_plan', 'follow_up_date']


class MedicalRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalRecord
        fields = ['id', 'patient', 'record_type', 'details', 'date_created']


class LabTestSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabTest
        fields = ['id', 'patient', 'test_name', 'result', 'date_conducted']


class PrescriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prescription
        fields = ['id', 'patient', 'medication_name', 'dosage', 'instructions', 'end_date']


class StaffMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffMessage
        fields = ['id', 'sender', 'recipient', 'message_content', 'sent_at']


class DoctorPatientMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorPatientMessage
        fields = ['id', 'sender', 'recipient', 'message_content', 'sent_at']


class TeamMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamMessage
        fields = ['id', 'sender', 'recipient', 'message_content', 'sent_at']


class InsuranceProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = InsuranceProvider
        fields = '__all__'

class InsuranceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Insurance
        fields = '__all__'

class BillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bill
        fields = '__all__'

class InsuranceClaimSerializer(serializers.ModelSerializer):
    class Meta:
        model = InsuranceClaim
        fields = '__all__'


class EmergencyAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmergencyAlert
        fields = ['id', 'profile', 'alert_type', 'message', 'status', 'created_at', 'updated_at', 'resolved_at']


class MedicalSupplySerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalSupply
        fields = '__all__'


class StockAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockAlert
        fields = '__all__'



class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = '__all__'


class HospitalPerformanceMetricsSerializer(serializers.ModelSerializer):
    class Meta:
        model = HospitalPerformanceMetrics
        fields = '__all__'

class ResourceAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceAllocation
        fields = '__all__'

class PerformanceAnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerformanceAnalytics
        fields = '__all__'


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = '__all__'



class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = '__all__'


class HealthAndSafetyProtocolSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthAndSafetyProtocol
        fields = '__all__'


class InfectionControlPracticeSerializer(serializers.ModelSerializer):
    protocol = HealthAndSafetyProtocolSerializer()

    class Meta:
        model = InfectionControlPractice
        fields = '__all__'



class CertificationSerializer(serializers.ModelSerializer):
    staff = StaffSerializer()

    class Meta:
        model = Certification
        fields = '__all__'


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'message', 'recipient', 'created_at', 'read', 'notification_type', 'is_urgent']


class PatientSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientProfile
        fields = '__all__'  # Or specify the fields you need

from rest_framework import serializers
from django.contrib.auth.models import User
from .models import *

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class ProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(source='user.user')

    class Meta:
        model = PatientProfile
        fields = [
            'user',
            'phone_number',
            'emergency_contact',
            'medical_history',
            'allergies',
            'insurance_details',
            'next_of_kin_name',
            'next_of_kin_phone_number',
            'next_of_kin_email',
            'next_of_kin_address',
            'next_of_kin_relationship',
        ]


class RegisterSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(required=True)  # Add phone_number field

    class Meta:
        model = User
        fields = ['username', 'password', 'email', 'phone_number']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password']
        )
        # Create a Patient instance linked to this user
        patient = PatientProfile.objects.create(user=user, phone_number=validated_data['phone_number'])

        return patient



class MedicationReminderSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicationReminder
        fields = ['id', 'patient', 'medication_name', 'dosage', 'time', 'reminder_text', 'is_taken']


class TreatmentPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreatmentPlan
        fields = ['id', 'patient', 'treatment_description', 'start_date', 'end_date', 'progress_notes']

# class BillSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Bill
#         fields = ['id', 'patient', 'total_amount', 'paid_amount', 'due_date', 'is_paid']


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = ['id', 'patient', 'rating', 'comments']


class EmergencyServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmergencyService
        fields = '__all__'
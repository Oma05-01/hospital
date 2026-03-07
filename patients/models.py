from django.contrib.auth.models import User
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

# Expanded choices for better data categorization
RELATIONSHIP_CHOICES = [
    ('Parent', 'Parent'),
    ('Sibling', 'Sibling'),
    ('Spouse', 'Spouse'),
    ('Child', 'Child'),
    ('Friend', 'Friend'),
    ('Other', 'Other'),
]

STATUS_CHOICES = [
    ('Active', 'Active'),
    ('Completed', 'Completed'),
    ('Cancelled', 'Cancelled'),
]

EMERGENCY_STATUS_CHOICES = [
    ('Pending', 'Pending'),
    ('Dispatched', 'Dispatched'),
    ('Resolved', 'Resolved'),
]


class PatientProfile(models.Model):
    """
    Merged Patient and Profile models.
    One-to-One with Django's built-in User model.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='patient_profile')

    # Basic Info
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    phone_number = models.CharField(max_length=15)

    # Medical Info
    medical_history = models.TextField(blank=True, null=True)
    allergies = models.TextField(blank=True, null=True)
    insurance_details = models.TextField(blank=True, null=True)

    # Emergency / Next of Kin Info
    emergency_contact = models.CharField(max_length=15, blank=True, null=True)
    next_of_kin_name = models.CharField(max_length=100, blank=True, null=True)
    next_of_kin_phone_number = models.CharField(max_length=15, blank=True, null=True)
    next_of_kin_email = models.EmailField(blank=True, null=True)
    next_of_kin_address = models.TextField(blank=True, null=True)
    next_of_kin_relationship = models.CharField(max_length=50, choices=RELATIONSHIP_CHOICES, blank=True, null=True)

    # Timestamps for auditing
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username}'s Profile"


class MedicationReminder(models.Model):
    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name='medication_reminders')
    medication_name = models.CharField(max_length=100)
    dosage = models.CharField(max_length=50)
    time = models.TimeField()
    reminder_text = models.TextField(blank=True, null=True)
    is_taken = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.medication_name} at {self.time} for {self.patient.user.username}"


class TreatmentPlan(models.Model):
    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name='treatment_plans')
    treatment_description = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)  # Added end date
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')  # Added status tracking
    progress_notes = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.status} Treatment Plan for {self.patient.user.username}"


class Feedback(models.Model):
    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name='feedback')
    # Added validators to ensure rating stays between 1 and 5
    rating = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comments = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    def __str__(self):
        return f"Rating: {self.rating}/5 from {self.patient.user.username}"


class EmergencyService(models.Model):
    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name='emergency_requests')
    location = models.CharField(max_length=255)
    emergency_type = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=EMERGENCY_STATUS_CHOICES, default='Pending')  # Crucial for ops
    request_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.status}] {self.emergency_type} for {self.patient.user.username}"


class TokenLog(models.Model):
    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name='token_logs', blank=True, null=True)
    token = models.TextField(default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Token for {self.patient.user.username} created on {self.created_at.date()}"


class Bill(models.Model):
    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name='patient_app_bills', blank=True, null=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # Added default
    due_date = models.DateField()
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    @property
    def balance_due(self):
        return self.total_amount - self.paid_amount

    def __str__(self):
        status = "Paid" if self.is_paid else "Unpaid"
        return f"{status} Bill: {self.patient.user.username} - Total: {self.total_amount}"
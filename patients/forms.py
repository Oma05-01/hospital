from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import PatientProfile, MedicationReminder, Feedback # Replace with your actual models

# Common widget attributes for consistent UI styling
DEFAULT_ATTRS = {'class': 'form-input'}

class UserRegistrationForm(forms.ModelForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'placeholder': 'johndoe@example.com'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Enter a strong password'}),
        label="Password"
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm your password'}),
        label="Confirm Password"
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']
        widgets = {
            'username': forms.TextInput(attrs={'placeholder': 'Choose a username'}),
            'first_name': forms.TextInput(attrs={'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Last Name'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError("A user with this email address already exists.")
        return email

    def clean_confirm_password(self):
        password = self.cleaned_data.get("password")
        confirm_password = self.cleaned_data.get("confirm_password")
        if password and confirm_password and password != confirm_password:
            raise ValidationError("Passwords do not match.")
        return confirm_password


class LoginForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'placeholder': 'Enter your username'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Enter your password'})
    )


class ProfileForm(forms.ModelForm):
    """
    Unified form for both creating and updating a Patient Profile.
    """
    class Meta:
        # CORRECTION: Pointing to PatientProfile instead of the deleted Profile model
        model = PatientProfile
        fields = [
            'phone_number',
            'emergency_contact',
            'medical_history',
            'allergies',
            'insurance_details',
            'next_of_kin_name',
            'next_of_kin_relationship',
            'next_of_kin_phone_number',
            'next_of_kin_email',
            'next_of_kin_address'
        ]
        labels = {
            'phone_number': 'Phone Number',
            'emergency_contact': 'Emergency Contact Number',
            'next_of_kin_name': 'Next of Kin Name',
            'next_of_kin_phone_number': 'Next of Kin Phone Number',
            'next_of_kin_email': 'Next of Kin Email',
            'next_of_kin_address': 'Next of Kin Address',
        }
        widgets = {
            'phone_number': forms.TextInput(attrs={'placeholder': 'e.g., 08012345678'}),
            'emergency_contact': forms.TextInput(attrs={'placeholder': 'Emergency contact number'}),
            'medical_history': forms.Textarea(attrs={'rows': 3, 'placeholder': 'List any previous major illnesses or surgeries...'}),
            'allergies': forms.Textarea(attrs={'rows': 2, 'placeholder': 'List any known allergies to medication or food...'}),
            'insurance_details': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Provider name, policy number...'}),
            'next_of_kin_email': forms.EmailInput(attrs={'placeholder': 'Email address'}),
            'next_of_kin_address': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Full residential address'}),
        }

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')
        # Stripping spaces/dashes to check pure digit length
        clean_number = ''.join(filter(str.isdigit, str(phone_number)))
        if phone_number and len(clean_number) < 11:
            raise ValidationError("Please enter a valid phone number (minimum 11 digits).")
        return phone_number


class MedicationReminderForm(forms.ModelForm):
    class Meta:
        model = MedicationReminder
        fields = ['medication_name', 'dosage', 'time', 'reminder_text']
        widgets = {
            'medication_name': forms.TextInput(attrs={'placeholder': 'e.g., Amoxicillin'}),
            'dosage': forms.TextInput(attrs={'placeholder': 'e.g., 500mg'}),
            # Use HTML5 time input for better mobile UX
            'time': forms.TimeInput(attrs={'type': 'time'}),
            'reminder_text': forms.Textarea(attrs={'rows': 2, 'placeholder': 'e.g., Take after meals'}),
        }


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ['rating', 'comments']
        widgets = {
            # Assuming rating is 1-5; HTML5 number input enforces this on the frontend
            'rating': forms.NumberInput(attrs={'min': 1, 'max': 5, 'placeholder': 'Rate 1 to 5'}),
            'comments': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Please share your experience with us...'}),
        }
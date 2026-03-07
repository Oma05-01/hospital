from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from patients.models import PatientProfile  # Adjust import path if needed
from .models import *
import re


class BillForm(forms.ModelForm):
    class Meta:
        model = Bill
        fields = ['item_description', 'quantity', 'unit_price', 'total_amount', 'status']
        # Adding some basic Bootstrap/Custom CSS classes for the frontend
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'item_description': forms.TextInput(attrs={'class': 'form-control'}),
        }


class InsuranceClaimForm(forms.ModelForm):
    class Meta:
        model = InsuranceClaim
        fields = ['claim_number', 'status']


class StaffUserCreationForm(forms.ModelForm):
    # Added First and Last name for professional hospital records
    first_name = forms.CharField(max_length=50, required=True, label="First Name")
    last_name = forms.CharField(max_length=50, required=True, label="Last Name")

    username = forms.CharField(
        widget=forms.TextInput(attrs={'placeholder': 'e.g., jdoe (No spaces)'}),
        label="Username"
    )
    email = forms.EmailField()
    password1 = forms.CharField(widget=forms.PasswordInput, label="Password")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Confirm Password")

    role = forms.ChoiceField(choices=Staff.ROLE_CHOICES, label="Role")
    specialty = forms.CharField(required=False, label="Specialty")
    phone_number = forms.CharField(label="Phone Number")
    profile_picture = forms.ImageField(required=False, label="Profile Picture")

    class Meta:
        model = Staff
        fields = ['role', 'specialty', 'phone_number', 'profile_picture']

    def clean_username(self):
        username = self.cleaned_data['username']
        # FIX: Ensure standard username format (no spaces) to prevent Django auth crashes
        if not re.match(r'^[\w.@+-]+$', username):
            raise forms.ValidationError("Username may only contain letters, numbers, and @/./+/-/_ characters.")
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2:
            if password1 != password2:
                raise forms.ValidationError("Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        # Create the user first, now including proper names
        user = User.objects.create_user(
            username=self.cleaned_data['username'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password1'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name']
        )

        # Save the staff model with the user and role information
        staff = super().save(commit=False)
        staff.user = user
        # role is already handled by super().save() because it's in Meta.fields!

        if commit:
            staff.save()
        return staff


class TeamMessageForm(forms.ModelForm):
    class Meta:
        model = TeamMessage
        fields = ['recipient', 'message_content']
        widgets = {
            'recipient': forms.Select(attrs={'class': 'staff-select form-control'}),
            'message_content': forms.Textarea(attrs={
                'placeholder': 'Enter internal clinical notes or instructions...',
                'rows': 3,
                'class': 'form-control'
            }),
        }

    def __init__(self, *args, **kwargs):
        exclude_user = kwargs.pop('exclude_user', None)
        super().__init__(*args, **kwargs)
        if exclude_user:
            self.fields['recipient'].queryset = Staff.objects.exclude(user=exclude_user)


class DoctorPatientMessageForm(forms.ModelForm):
    """
    Simplified! Because we handle the sender and recipient assignment
    directly in the `views.py` (which is much safer), we don't need
    the complex __init__ and save overrides here anymore.
    """

    class Meta:
        model = DoctorPatientMessage
        fields = ['message_content']
        widgets = {
            'message_content': forms.Textarea(attrs={
                'placeholder': 'Type your message to the patient here...',
                'rows': 4,
                'class': 'form-control'
            })
        }
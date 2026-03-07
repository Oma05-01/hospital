from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import MedicalRecord, HealthReport, Prescription

# ==========================================
# PATIENT-FACING VIEWS (STRICTLY READ-ONLY)
# ==========================================

@login_required
def medical_records(request):
    # Security check: Ensure the user actually has a patient profile
    # Change 'patient' to 'patient_profile' if you used a custom related_name
    if not hasattr(request.user, 'patient_profile'):
        messages.error(request, "Only registered patients can access this portal.")
        return redirect('patients:home')  # Or your desired fallback URL

    # Fetch records and order by the newest first
    records = MedicalRecord.objects.filter(
        patient=request.user.patient_profile
    ).order_by('-date_recorded')

    return render(request, 'records/medical_records.html', {'records': records})


@login_required
def health_reports(request):
    if not hasattr(request.user, 'patient_profile'):
        messages.error(request, "Only registered patients can access health reports.")
        return redirect('patients:home')

    # Order by newest uploads first
    reports = HealthReport.objects.filter(
        patient=request.user.patient_profile
    ).order_by('-uploaded_at')

    return render(request, 'records/health_reports.html', {'reports': reports})


@login_required
def prescriptions(request):
    if not hasattr(request.user, 'patient_profile'):
        messages.error(request, "Only registered patients can access prescriptions.")
        return redirect('patients:home')

    # Order by newest issuance first
    prescriptions = Prescription.objects.filter(
        patient=request.user.patient_profile
    ).order_by('-issued_at')

    return render(request, 'records/prescriptions.html', {'prescriptions': prescriptions})
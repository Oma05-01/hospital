# from weasyprint import HTML
from django.template.loader import render_to_string
from django.conf import settings
import os
from .models import *
from patients.models import PatientProfile

def generate_report_pdf(report):
    context = {
        'report': report,
        'data': fetch_data_for_report(report.report_type),  # Custom function to gather data
    }
    html_string = render_to_string('report_template.html', context)
    pdf_file_path = os.path.join(settings.MEDIA_ROOT, 'reports', f"{report.title}.pdf")
    # HTML(string=html_string).write_pdf(pdf_file_path)
    return pdf_file_path

def fetch_data_for_report(report_type):
    if report_type == 'patient_care':
        # Example: Fetch patient care data
        return PatientProfile.objects.all()
    elif report_type == 'financial':
        # Example: Fetch financial data
        return Bill.objects.all()
    elif report_type == 'performance':
        # Example: Fetch performance data
        return PerformanceAnalytics.objects.all()

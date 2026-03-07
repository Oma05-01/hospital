import logging
from django.db.models.signals import post_save, pre_delete, post_delete
from django.dispatch import receiver
from django.db import IntegrityError

from .models import AuditLog, Appointment

# Set up professional logging to replace print() statements
logger = logging.getLogger(__name__)


# ==========================================
# 1. GLOBAL AUDIT LOGGING
# ==========================================

@receiver(post_save)
def create_audit_log(sender, instance, created, **kwargs):
    """Logs creation and updates for all models in the staff app."""
    if sender._meta.app_label == 'staff' and sender.__name__ != 'AuditLog':
        user = getattr(instance, 'updated_by', getattr(instance, 'created_by', None))
        AuditLog.objects.create(
            user=user,
            action='Created' if created else 'Updated',
            model_name=sender.__name__,
            model_instance_id=instance.id
        )


@receiver(pre_delete)
def delete_audit_log(sender, instance, **kwargs):
    """Logs deletions for all models in the staff app."""
    if sender._meta.app_label == 'staff' and sender.__name__ != 'AuditLog':
        user = getattr(instance, 'updated_by', getattr(instance, 'created_by', None))
        AuditLog.objects.create(
            user=user,
            action='Deleted',
            model_name=sender.__name__,
            model_instance_id=instance.id
        )


# ==========================================
# 2. PATIENT EMAIL NOTIFICATIONS
# ==========================================

@receiver(post_save, sender=Appointment)
def send_appointment_reminder(sender, instance, created, **kwargs):
    """Sends a confirmation email to the patient when an appointment is booked."""
    if created:
        try:
            # Safely access the user's name and email through the relationships
            patient_name = instance.patient.user.get_full_name() or instance.patient.user.username
            patient_email = instance.patient.user.email
            doctor_name = instance.doctor.user.last_name

            subject = "Appointment Confirmation - CareFirst Medical"

            # Use getattr to safely handle datetime fields based on your exact model structure
            # Adjust these field names (scheduled_time vs date/time) to match your single model
            apt_time = getattr(instance, 'scheduled_time', None)
            time_str = apt_time.strftime('%B %d, %Y at %I:%M %p') if apt_time else "your scheduled time"

            message = (
                f"Dear {patient_name},\n\n"
                f"Your appointment with Dr. {doctor_name} is confirmed for {time_str}.\n\n"
                f"Thank you,\nCareFirst Medical Administration"
            )

            if patient_email:
                # send_mail(
                #     subject,
                #     message,
                #     settings.DEFAULT_FROM_EMAIL,
                #     [patient_email],
                #     fail_silently=False
                # )
                logger.info(f"Email reminder staged for Appointment #{instance.id}")
            else:
                logger.warning(f"Cannot send email: No email address on file for {patient_name}")

        except Exception as e:
            logger.error(f"Failed to prepare/send email for Appointment #{instance.id}: {e}")

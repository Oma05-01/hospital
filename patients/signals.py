from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import PatientProfile

# @receiver(post_save, sender=User)
# def manage_user_profile(sender, instance, created, **kwargs):
#     """
#     Creates a Profile whenever a new User is created.
#     This works for both Staff and Patients.
#     """
#     if created:
#         PatientProfile.objects.create(user=instance)
#     else:
#         # Safely save the profile during user updates
#         if hasattr(instance, 'profile'):
#             instance.profile.save()

@receiver(post_save, sender=User)
def auto_create_patient_model(sender, instance, created, **kwargs):
    """
    If you want every new User to automatically have a Patient entry
    (unless they are staff), you can handle that here.
    """
    if created:
        # Only create a Patient entry if they aren't marked as staff/superuser
        if not instance.is_staff and not instance.is_superuser:
            PatientProfile.objects.get_or_create(user=instance)
from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail


@shared_task(autoretry_for=(OSError,), retry_backoff=True, max_retries=3)
def send_approval_email(user_id):
    user = get_user_model().objects.filter(pk=user_id, approval_status="approved", is_active=True).first()
    if user:
        send_mail(
            "Your AirBooking account is ready",
            f"Hi {user.first_name or user.username}, your AirBooking account has been activated. You can now sign in and book flights.",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from booking.models import Flight, User


class Command(BaseCommand):
    help = "Create the local evaluation administrator and sample flights."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo seeding requires DJANGO_DEBUG=true.")
        admin, created = User.objects.get_or_create(
            username="evaluator", defaults={"email": "evaluator@example.test"},
        )
        if created:
            admin.set_password("AirBooking-Demo-482!")
            admin.is_staff = admin.is_superuser = True
            admin.approval_status = User.Approval.APPROVED
            admin.save()
        elif not (admin.is_staff and admin.is_active and admin.approval_status == User.Approval.APPROVED):
            raise CommandError("The evaluator username is already in use. Use another database or create your own administrator.")

        morning = (timezone.localtime() + timedelta(days=1)).replace(hour=9, minute=30, second=0, microsecond=0)
        examples = [
            ("AB217", "Horizon Air", "COK", "BLR", 0, 0, 65, "4299", 36),
            ("AB402", "Coastline Air", "COK", "BOM", 0, 3, 115, "5899", 24),
            ("AB361", "Horizon Air", "CCJ", "DXB", 1, 1, 235, "12999", 42),
            ("AB580", "Northstar Air", "BLR", "DEL", 1, 4, 170, "6699", 18),
            ("AB720", "Coastline Air", "BLR", "COK", 2, 2, 65, "4599", 30),
        ]
        for number, airline, origin, destination, days, hours, duration, price, capacity in examples:
            departure = morning + timedelta(days=days, hours=hours)
            Flight.objects.get_or_create(number=number, departure=departure, defaults={
                "airline": airline, "origin": origin, "destination": destination,
                "arrival": departure + timedelta(minutes=duration), "price": Decimal(price),
                "capacity": capacity, "seats_available": capacity, "demo": True,
            })
        self.stdout.write(self.style.SUCCESS("Sample flights ready. Demo administrator username: evaluator"))

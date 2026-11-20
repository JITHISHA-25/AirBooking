from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from booking.models import Flight, FlightMeal, Meal


class Command(BaseCommand):
    help = "Create demo meals for future demo flights, or explicitly assign them to all existing flights."

    def add_arguments(self, parser):
        parser.add_argument("--all-flights", action="store_true",
                            help="Assign the demo menu to every existing flight; keep ordering cutoffs and closure settings unchanged.")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo seeding requires DJANGO_DEBUG=true.")
        samples = [
            ("Demo vegetable biryani", "Fragrant rice with mixed vegetables.", "vegetarian", "250.00", "Rice, vegetables, spices. Contains dairy; prepared in a shared kitchen."),
            ("Demo chicken rice", "Chicken with steamed rice.", "non_vegetarian", "350.00", "Chicken, rice, spices. Contains dairy; may contain nuts."),
            ("Demo vegetable sandwich", "Vegetable sandwich and fruit.", "vegetarian", "180.00", "Wheat bread, vegetables, fruit. Contains gluten and dairy."),
        ]
        meals = []
        for name, description, category, price, notes in samples:
            meal, _ = Meal.objects.get_or_create(name=name, defaults={"description": description, "category": category,
                "price": price, "ingredient_notes": notes})
            meals.append(meal)
        count = 0
        flights = Flight.objects.all() if options["all_flights"] else Flight.objects.filter(demo=True, departure__gt=timezone.now())
        flight_count = 0
        for flight in flights.select_for_update():
            flight_count += 1
            for meal in meals:
                _, created = FlightMeal.objects.get_or_create(flight=flight, meal=meal)
                count += int(created)
        self.stdout.write(self.style.SUCCESS(f"Demo meals ready for {flight_count} flights; {count} new flight assignments. No airline fulfillment is arranged."))

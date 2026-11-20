import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import F, Q


class User(AbstractUser):
    class Approval(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    email = models.EmailField(unique=True)
    approval_status = models.CharField(max_length=10, choices=Approval, default=Approval.PENDING)

    class Meta:
        constraints = [
            models.UniqueConstraint(models.functions.Lower("email"), name="unique_user_email_lower"),
        ]


class Flight(models.Model):
    class Cabin(models.TextChoices):
        ECONOMY = "economy", "Economy"
        PREMIUM_ECONOMY = "premium_economy", "Premium Economy"
        BUSINESS = "business", "Business Class"
        FIRST = "first", "First Class"

    class Status(models.TextChoices):
        ON_TIME = "on_time", "On time"
        DELAYED = "delayed", "Delayed"
        CANCELLED = "cancelled", "Cancelled"
        DEPARTED = "departed", "Departed"
        LANDED = "landed", "Landed"

    number = models.CharField(max_length=8)
    airline = models.CharField(max_length=80)
    cabin_class = models.CharField(max_length=20, choices=Cabin, default=Cabin.ECONOMY)
    origin = models.CharField(max_length=3)
    destination = models.CharField(max_length=3)
    departure = models.DateTimeField(db_index=True)
    arrival = models.DateTimeField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    capacity = models.PositiveIntegerField()
    seats_available = models.PositiveIntegerField()
    status = models.CharField(max_length=12, choices=Status, default=Status.ON_TIME)
    status_updated_at = models.DateTimeField(auto_now_add=True)
    demo = models.BooleanField(default=False, editable=False)
    food_ordering_open = models.BooleanField(default=True)

    class Meta:
        ordering = ["departure", "id"]
        constraints = [
            models.UniqueConstraint(fields=["number", "departure"], name="unique_flight_instance"),
            models.CheckConstraint(condition=Q(arrival__gt=F("departure")), name="flight_arrival_after_departure"),
            models.CheckConstraint(condition=Q(seats_available__lte=F("capacity")), name="flight_seats_within_capacity"),
            models.CheckConstraint(condition=Q(capacity__gte=1, price__gt=0), name="flight_positive_capacity_price"),
            models.CheckConstraint(condition=~Q(origin=F("destination")), name="flight_different_airports"),
        ]


class Complaint(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="complaints")
    subject = models.CharField(max_length=160)
    message = models.TextField(max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Booking(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    class Payment(models.TextChoices):
        PAID = "paid", "Paid (simulated)"
        REFUNDED = "refunded", "Refunded (simulated)"

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="bookings")
    flight = models.ForeignKey(Flight, on_delete=models.PROTECT, related_name="bookings")
    seats = models.PositiveSmallIntegerField()
    adults = models.PositiveSmallIntegerField(default=1)
    children = models.PositiveSmallIntegerField(default=0)
    infants = models.PositiveSmallIntegerField(default=0)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status, default=Status.CONFIRMED)
    payment_status = models.CharField(max_length=10, choices=Payment, default=Payment.PAID)
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=500, blank=True, default="")
    request_id = models.UUIDField()
    request_payload = models.JSONField(default=dict, blank=True, editable=False)

    @property
    def total(self):
        return self.unit_price * self.seats

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "request_id"], name="unique_user_booking_request"),
            models.CheckConstraint(condition=Q(seats__range=(1, 9)), name="booking_seat_count"),
        ]


class Meal(models.Model):
    class Category(models.TextChoices):
        VEGETARIAN = "vegetarian", "Vegetarian"
        NON_VEGETARIAN = "non_vegetarian", "Non-vegetarian"

    name = models.CharField(max_length=120)
    description = models.TextField(max_length=2000, blank=True)
    category = models.CharField(max_length=16, choices=Category)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    ingredient_notes = models.TextField(max_length=2000, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [models.CheckConstraint(condition=Q(price__gt=0), name="meal_positive_price")]


class FlightMeal(models.Model):
    flight = models.ForeignKey(Flight, on_delete=models.CASCADE, related_name="meal_availability")
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE, related_name="flight_availability")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["flight", "meal"], name="unique_flight_meal")]


class FoodOrder(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"

    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="food_orders")
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="food_orders")
    status = models.CharField(max_length=10, choices=Status, default=Status.ACTIVE)
    payment_status = models.CharField(max_length=10, choices=Booking.Payment, default=Booking.Payment.PAID)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    request_id = models.UUIDField()
    request_payload = models.JSONField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "request_id"], name="unique_user_food_request"),
            models.UniqueConstraint(fields=["booking"], condition=Q(status="active"), name="one_active_food_order"),
            models.CheckConstraint(condition=Q(total__gt=0), name="food_order_positive_total"),
            models.CheckConstraint(condition=(Q(status="active", payment_status="paid", cancelled_at__isnull=True, refunded_at__isnull=True)
                | Q(status="cancelled", payment_status="refunded", cancelled_at__isnull=False, refunded_at__isnull=False)),
                name="food_order_consistent_refund"),
        ]


class FoodOrderItem(models.Model):
    order = models.ForeignKey(FoodOrder, on_delete=models.CASCADE, related_name="items")
    meal = models.ForeignKey(Meal, on_delete=models.PROTECT, related_name="order_items")
    purchased_name = models.CharField(max_length=120)
    quantity = models.PositiveSmallIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["order", "meal"], name="unique_order_meal"),
            models.CheckConstraint(condition=Q(quantity__range=(1, 9), unit_price__gt=0), name="food_item_valid_amounts"),
        ]

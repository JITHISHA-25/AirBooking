from decimal import Decimal
import re

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer

from .auth import eligible
from .models import Booking, Complaint, Flight, User
from .food import FoodOrderSerializer, MealSelection, canonical_items, food_closed_reason, food_cutoff, refund_food_orders


class ComplaintSerializer(serializers.ModelSerializer):
    class Meta:
        model = Complaint
        fields = ["id", "subject", "message", "created_at"]
        read_only_fields = ["id", "created_at"]


class AdminComplaintSerializer(ComplaintSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta(ComplaintSerializer.Meta):
        fields = [*ComplaintSerializer.Meta.fields, "username", "email"]
        read_only_fields = fields


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "approval_status", "is_staff", "is_active"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "password"]

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account already uses this email.")
        return value

    def validate(self, attrs):
        user = User(**{key: value for key, value in attrs.items() if key != "password"})
        validate_password(attrs["password"], user)
        return attrs

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return User.objects.create_user(**validated_data)
        except IntegrityError as exc:
            raise serializers.ValidationError("This username or email already exists.") from exc


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        user = authenticate(request=self.context.get("request"), **attrs)
        if user is None:
            raise PermissionDenied("Invalid username or password.")
        if not eligible(user):
            raise PermissionDenied(
                "Your account is pending approval." if user.approval_status == User.Approval.PENDING
                else "Your account was rejected. Contact the administrator."
            )
        refresh = self.get_token(user)
        return {"refresh": str(refresh), "access": str(refresh.access_token), "user": UserSerializer(user).data}


class RefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        refresh = self.token_class(attrs["refresh"])
        user = User.objects.filter(pk=refresh.get("user_id")).first()
        if user is None or not eligible(user):
            raise PermissionDenied("This account cannot refresh its session.")
        return super().validate(attrs)


class FlightSerializer(serializers.ModelSerializer):
    number = serializers.RegexField(r"^[A-Z0-9]{2}[0-9]{1,4}[A-Z]?$", max_length=8)
    origin = serializers.RegexField(r"^[A-Z]{3}$")
    destination = serializers.RegexField(r"^[A-Z]{3}$")
    capacity = serializers.IntegerField(min_value=1, max_value=1000)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))

    class Meta:
        model = Flight
        fields = ["id", "number", "airline", "cabin_class", "origin", "destination", "departure", "arrival",
                  "price", "capacity", "seats_available", "status", "status_updated_at", "demo", "food_ordering_open"]
        read_only_fields = ["seats_available", "status_updated_at", "demo"]

    def validate(self, attrs):
        def value(field):
            return attrs.get(field, getattr(self.instance, field, None))

        if value("arrival") <= value("departure"):
            raise serializers.ValidationError({"arrival": "Arrival must be after departure."})
        if value("origin") == value("destination"):
            raise serializers.ValidationError({"destination": "Choose a different airport."})
        matches = Flight.objects.filter(number=value("number"), departure=value("departure"))
        if self.instance:
            matches = matches.exclude(pk=self.instance.pk)
            sold = self.instance.capacity - self.instance.seats_available
            if sold and value("cabin_class") != self.instance.cabin_class:
                raise serializers.ValidationError({"cabin_class": "The cabin class cannot change while seats are reserved."})
            if value("capacity") < sold:
                raise serializers.ValidationError({"capacity": f"At least {sold} seats are already reserved."})
        if matches.exists():
            raise serializers.ValidationError({"number": "This flight and departure already exist."})
        return attrs

    def create(self, validated_data):
        if validated_data.get("status") == Flight.Status.CANCELLED:
            validated_data["food_ordering_open"] = False
        return super().create({**validated_data, "seats_available": validated_data["capacity"]})

    def update(self, instance, validated_data):
        from django.utils import timezone

        if "capacity" in validated_data:
            sold = instance.capacity - instance.seats_available
            validated_data["seats_available"] = validated_data["capacity"] - sold
        if validated_data.get("status", instance.status) != instance.status:
            validated_data["status_updated_at"] = timezone.now()
        if validated_data.get("status", instance.status) == Flight.Status.CANCELLED:
            validated_data["food_ordering_open"] = False
        flight = super().update(instance, validated_data)
        if flight.status == Flight.Status.CANCELLED:
            from .models import FoodOrder
            refund_food_orders(FoodOrder.objects.filter(booking__flight=flight), "Flight cancelled by administrator")
        return flight


class TravellerInput(serializers.Serializer):
    adults = serializers.IntegerField(min_value=1, max_value=9, required=False)
    children = serializers.IntegerField(min_value=0, max_value=6, required=False)
    infants = serializers.IntegerField(min_value=0, max_value=6, required=False)
    seats = serializers.IntegerField(min_value=1, max_value=9, required=False)

    def validate(self, attrs):
        if any(field in attrs for field in ("adults", "children", "infants")):
            adults = attrs.get("adults", 1)
            children = attrs.get("children", 0)
            infants = attrs.get("infants", 0)
            total = adults + children + infants
            if total > 9:
                raise serializers.ValidationError("Online bookings support up to 9 travellers.")
            if infants > adults:
                raise serializers.ValidationError({"infants": "Each infant must be accompanied by an adult."})
            if "seats" in attrs and attrs["seats"] != total:
                raise serializers.ValidationError({"seats": "Seats must match the total number of travellers."})
            attrs.update(adults=adults, children=children, infants=infants, seats=total)
        else:
            attrs.update(adults=attrs.get("seats", 1), children=0, infants=0, seats=attrs.get("seats", 1))
        return attrs


class SearchSerializer(TravellerInput):
    origin = serializers.RegexField(r"^[A-Z]{3}$", required=False)
    destination = serializers.RegexField(r"^[A-Z]{3}$", required=False)
    airport = serializers.RegexField(r"^[A-Z]{3}$", required=False)
    date = serializers.DateField(required=False)
    cabin_class = serializers.ChoiceField(choices=Flight.Cabin, required=False)
    available = serializers.BooleanField(required=False)


class BookingInput(TravellerInput):
    flight_id = serializers.IntegerField(min_value=1)
    request_id = serializers.UUIDField(required=False)
    payment = serializers.ChoiceField(choices=["success", "decline"], default="success")
    meals = MealSelection(many=True, default=list, max_length=9)

    def validate_meals(self, value):
        return canonical_items(value)


class CancellationInput(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class StatusSearchInput(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["airport", "route", "flight_number"])
    date = serializers.DateField()
    direction = serializers.ChoiceField(choices=["departures", "arrivals"], default="departures")
    airport = serializers.RegexField(r"^[A-Z]{3}$", required=False)
    origin = serializers.RegexField(r"^[A-Z]{3}$", required=False)
    destination = serializers.RegexField(r"^[A-Z]{3}$", required=False)
    flight_number = serializers.RegexField(r"^[A-Z0-9]{2}[0-9]{1,4}[A-Z]?$", required=False, max_length=8)

    def to_internal_value(self, data):
        data = data.copy()
        for field in ("airport", "origin", "destination", "flight_number"):
            if isinstance(data.get(field), str):
                data[field] = re.sub(r"\s+", "", data[field]).upper()
        return super().to_internal_value(data)

    def validate(self, attrs):
        required = {"airport": ["airport"], "route": ["origin", "destination"], "flight_number": ["flight_number"]}[attrs["mode"]]
        errors = {field: "This field is required." for field in required if not attrs.get(field)}
        if errors:
            raise serializers.ValidationError(errors)
        if attrs["mode"] == "route" and attrs["origin"] == attrs["destination"]:
            raise serializers.ValidationError({"destination": "Choose a different airport."})
        return attrs


class BookingSerializer(serializers.ModelSerializer):
    flight = FlightSerializer(read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    food_orders = FoodOrderSerializer(many=True, read_only=True)
    food_total = serializers.SerializerMethodField()
    combined_total = serializers.SerializerMethodField()
    food_cutoff = serializers.SerializerMethodField()
    food_available = serializers.SerializerMethodField()
    food_unavailable_reason = serializers.SerializerMethodField()

    def get_food_total(self, booking):
        return str(sum((order.total for order in booking.food_orders.all() if order.status == "active"), Decimal("0.00")))

    def get_combined_total(self, booking):
        return str(booking.total + Decimal(self.get_food_total(booking)))

    def get_food_cutoff(self, booking):
        return food_cutoff(booking.flight).isoformat()

    def get_food_available(self, booking):
        return not food_closed_reason(booking.flight, booking) and not any(order.status == "active" for order in booking.food_orders.all())

    def get_food_unavailable_reason(self, booking):
        return food_closed_reason(booking.flight, booking) or ("An active food order already exists." if any(
            order.status == "active" for order in booking.food_orders.all()) else "")

    class Meta:
        model = Booking
        fields = ["id", "reference", "flight", "seats", "adults", "children", "infants", "unit_price", "total", "status",
                  "payment_status", "created_at", "cancelled_at", "cancellation_reason", "food_orders", "food_total",
                  "combined_total", "food_cutoff", "food_available", "food_unavailable_reason"]
        read_only_fields = ["cancellation_reason"]

"""Demo food ordering: snapshots, owner access, and flight-first transactional locks."""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, serializers, viewsets
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Booking, Flight, FlightMeal, FoodOrder, FoodOrderItem, Meal, User
from .payments import simulate_payment


class FoodConflict(APIException):
    status_code = 409


def food_cutoff(flight):
    return flight.departure - timedelta(hours=settings.FOOD_ORDER_CUTOFF_HOURS)


def food_closed_reason(flight, booking=None):
    if booking is not None and booking.status != Booking.Status.CONFIRMED:
        return "Food ordering requires a confirmed booking."
    if flight.status not in {Flight.Status.ON_TIME, Flight.Status.DELAYED}:
        return "Food ordering is closed for this flight status."
    if not flight.food_ordering_open:
        return "Food ordering has been closed by the administrator."
    if timezone.now() >= food_cutoff(flight):
        return "The food ordering and cancellation cutoff has passed."
    return ""


class MealSelection(serializers.Serializer):
    meal_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=9)


def canonical_items(items):
    if len({item["meal_id"] for item in items}) != len(items):
        raise serializers.ValidationError({"items": "Select each meal only once."})
    return sorted(items, key=lambda item: item["meal_id"])


class FoodInput(serializers.Serializer):
    items = MealSelection(many=True, allow_empty=False, max_length=9)
    request_id = serializers.UUIDField()
    payment = serializers.ChoiceField(choices=["success", "decline"], default="success")

    def validate_items(self, value):
        return canonical_items(value)


class MealSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))

    class Meta:
        model = Meal
        fields = ["id", "name", "description", "category", "price", "ingredient_notes", "active"]


class FoodItemSerializer(serializers.ModelSerializer):
    line_total = serializers.SerializerMethodField()

    def get_line_total(self, item):
        return str(item.unit_price * item.quantity)

    class Meta:
        model = FoodOrderItem
        fields = ["meal_id", "purchased_name", "quantity", "unit_price", "line_total"]


class FoodOrderSerializer(serializers.ModelSerializer):
    items = FoodItemSerializer(many=True, read_only=True)

    class Meta:
        model = FoodOrder
        fields = ["id", "booking_id", "status", "payment_status", "total", "items", "created_at",
                  "cancelled_at", "refunded_at", "cancellation_reason"]


def refund_food_orders(queryset, reason):
    now = timezone.now()
    queryset.filter(status=FoodOrder.Status.ACTIVE).update(status=FoodOrder.Status.CANCELLED,
        payment_status=Booking.Payment.REFUNDED, cancelled_at=now, refunded_at=now, cancellation_reason=reason)


def purchase_food(booking, items, request_id, payment="success"):
    """Caller holds flight then booking locks in an atomic transaction."""
    items = canonical_items(items)
    fingerprint = {"booking_id": booking.pk, "items": items, "payment": payment}
    previous = FoodOrder.objects.filter(user_id=booking.user_id, request_id=request_id).first()
    if previous:
        if previous.request_payload != fingerprint:
            raise FoodConflict("This request ID was already used for a different food order payload.")
        return previous, False
    reason = food_closed_reason(booking.flight, booking)
    if reason:
        raise FoodConflict(reason)
    if booking.food_orders.filter(status=FoodOrder.Status.ACTIVE).exists():
        raise FoodConflict("This booking already has an active food order. Cancel it before placing another.")
    if not items or sum(item["quantity"] for item in items) > booking.seats:
        raise serializers.ValidationError({"items": "Choose at least one meal, with at most one meal per reserved seat in total."})
    # Assignment mutations lock the flight; catalog mutations lock the same meal rows.
    meals = {meal.pk: meal for meal in Meal.objects.select_for_update().filter(
        active=True, flight_availability__flight=booking.flight, pk__in=[item["meal_id"] for item in items]).order_by("pk")}
    if len(meals) != len(items):
        raise serializers.ValidationError({"items": "A selected meal is inactive or is not available for this flight. Refresh the menu."})
    # A catalog edit may have held its row lock until after the cutoff.
    reason = food_closed_reason(booking.flight, booking)
    if reason:
        raise FoodConflict(reason)
    total = sum((meals[item["meal_id"]].price * item["quantity"] for item in items), Decimal("0.00"))
    simulate_payment(payment, food_only=True)
    order = FoodOrder.objects.create(booking=booking, user_id=booking.user_id, request_id=request_id, request_payload=fingerprint, total=total)
    FoodOrderItem.objects.bulk_create([FoodOrderItem(order=order, meal=meals[item["meal_id"]],
        purchased_name=meals[item["meal_id"]].name, unit_price=meals[item["meal_id"]].price,
        quantity=item["quantity"]) for item in items])
    return order, True


class FlightMenu(APIView):
    def get(self, request, pk):
        flight = get_object_or_404(Flight, pk=pk)
        reason = food_closed_reason(flight)
        meals = Meal.objects.filter(active=True, flight_availability__flight=flight)
        return Response({"cutoff": food_cutoff(flight), "available": not bool(reason), "reason": reason,
                         "meals": MealSerializer(meals, many=True).data})


class BookingFood(APIView):
    def owned(self, request, pk):
        return get_object_or_404(Booking.objects.select_related("flight"), pk=pk, user=request.user)

    def get(self, request, pk):
        booking = self.owned(request, pk)
        return Response(FoodOrderSerializer(booking.food_orders.prefetch_related("items"), many=True).data)

    def post(self, request, pk):
        data = FoodInput(data=request.data)
        data.is_valid(raise_exception=True)
        found = self.owned(request, pk)
        with transaction.atomic():
            # Match initial booking's user -> flight -> booking lock order and serialize request IDs per owner.
            User.objects.select_for_update().get(pk=request.user.pk)
            flight = Flight.objects.select_for_update().get(pk=found.flight_id)
            booking = Booking.objects.select_for_update().get(pk=found.pk, user=request.user)
            booking.flight = flight
            order, created = purchase_food(booking, **data.validated_data)
            response = FoodOrderSerializer(order).data
        return Response(response, status=201 if created else 200)


class CancelFood(BookingFood):
    http_method_names = ["post", "options"]

    def post(self, request, pk, order_id):
        found = self.owned(request, pk)
        with transaction.atomic():
            flight = Flight.objects.select_for_update().get(pk=found.flight_id)
            booking = Booking.objects.select_for_update().get(pk=found.pk, user=request.user)
            order = get_object_or_404(FoodOrder.objects.select_for_update(), pk=order_id, booking=booking)
            if order.status == FoodOrder.Status.ACTIVE:
                if timezone.now() >= food_cutoff(flight):
                    raise FoodConflict("The food cancellation cutoff has passed.")
                refund_food_orders(FoodOrder.objects.filter(pk=order.pk), "Cancelled by traveler")
                order.refresh_from_db()
            response = FoodOrderSerializer(order).data
        return Response(response)


class AdminMeals(mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = MealSerializer
    queryset = Meal.objects.all()

    def update(self, request, *args, **kwargs):
        with transaction.atomic():
            self.queryset = Meal.objects.select_for_update()
            return super().update(request, *args, **kwargs)


class MenuAssignmentInput(serializers.Serializer):
    meal_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=True, max_length=200)
    food_ordering_open = serializers.BooleanField(required=False)

    def validate_meal_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Choose each meal only once.")
        return value


class AdminFlightMeals(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        flight = get_object_or_404(Flight, pk=pk)
        return Response({"meal_ids": list(flight.meal_availability.values_list("meal_id", flat=True)),
                         "food_ordering_open": flight.food_ordering_open})

    def put(self, request, pk):
        data = MenuAssignmentInput(data=request.data)
        data.is_valid(raise_exception=True)
        ids = data.validated_data["meal_ids"]
        with transaction.atomic():
            flight = get_object_or_404(Flight.objects.select_for_update(), pk=pk)
            if Meal.objects.filter(pk__in=ids).count() != len(ids):
                raise serializers.ValidationError({"meal_ids": "One or more meals do not exist."})
            if data.validated_data.get("food_ordering_open") and flight.status == Flight.Status.CANCELLED:
                raise FoodConflict("Cannot open food ordering on a cancelled flight.")
            flight.meal_availability.exclude(meal_id__in=ids).delete()
            FlightMeal.objects.bulk_create([FlightMeal(flight=flight, meal_id=meal_id) for meal_id in ids], ignore_conflicts=True)
            if "food_ordering_open" in data.validated_data:
                flight.food_ordering_open = data.validated_data["food_ordering_open"]
                flight.save(update_fields=["food_ordering_open"])
        return self.get(request, pk)


class AdminFlightFood(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        flight = get_object_or_404(Flight, pk=pk)
        orders = FoodOrder.objects.filter(booking__flight=flight).prefetch_related("items")
        requirements = FoodOrderItem.objects.filter(order__booking__flight=flight, order__status=FoodOrder.Status.ACTIVE,
            order__booking__status=Booking.Status.CONFIRMED).exclude(order__booking__flight__status=Flight.Status.CANCELLED)
        totals = requirements.values("meal_id", "purchased_name").annotate(quantity=Sum("quantity")).order_by("meal_id", "purchased_name")
        return Response({"orders": FoodOrderSerializer(orders, many=True).data, "requirements": list(totals)})

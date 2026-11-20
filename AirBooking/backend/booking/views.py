import logging
import uuid

from django.db import IntegrityError, transaction
from django.db.models import Q, ProtectedError, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .auth import eligible
from .live import flight_status
from .models import Booking, Complaint, Flight, User
from .models import FoodOrder
from .food import purchase_food, refund_food_orders
from .payments import PaymentDeclined, simulate_payment
from .serializers import (
    AdminComplaintSerializer, BookingInput, BookingSerializer, ComplaintSerializer, FlightSerializer, LoginSerializer, RefreshSerializer,
    CancellationInput, RegisterSerializer, SearchSerializer, UserSerializer,
)
from .tasks import send_approval_email
from .status_search import search_status
from .serializers import StatusSearchInput

logger = logging.getLogger(__name__)


class FlightStatusSearch(APIView):
    def get(self, request):
        payload = StatusSearchInput(data=request.query_params)
        payload.is_valid(raise_exception=True)
        return Response(search_status(payload.validated_data))


class Complaints(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ComplaintSerializer

    def get_queryset(self):
        return Complaint.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AdminComplaints(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = AdminComplaintSerializer
    queryset = Complaint.objects.select_related("user").all()


class Conflict(APIException):
    status_code = 409
    default_detail = "This action conflicts with the current state."


class Register(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def create(self, request, *args, **kwargs):
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        user = payload.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class Login(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


class Refresh(TokenRefreshView):
    serializer_class = RefreshSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


class Me(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class LogoutPayload(serializers.Serializer):
    refresh = serializers.CharField(trim_whitespace=False)


class Logout(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        payload = LogoutPayload(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            RefreshToken(payload.validated_data["refresh"]).blacklist()
        except TokenError as exc:
            raise serializers.ValidationError({"refresh": "This refresh token is invalid or expired."}) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class FlightSearch(generics.ListAPIView):
    serializer_class = FlightSerializer

    def get_queryset(self):
        query = self.request.query_params.dict()
        for field in ("origin", "destination", "airport"):
            if field in query:
                query[field] = query[field].strip().upper()
        filters = SearchSerializer(data=query)
        filters.is_valid(raise_exception=True)
        values = filters.validated_data
        flights = Flight.objects.filter(departure__gt=timezone.now())
        for field in ("origin", "destination"):
            if field in values:
                flights = flights.filter(**{field: values[field]})
        if airport := values.get("airport"):
            flights = flights.filter(Q(origin=airport) | Q(destination=airport))
        if date := values.get("date"):
            flights = flights.filter(departure__date=date)
        if cabin := values.get("cabin_class"):
            flights = flights.filter(cabin_class=cabin)
        if values.get("available", True):
            flights = flights.filter(
                status__in=[Flight.Status.ON_TIME, Flight.Status.DELAYED],
                seats_available__gte=values.get("seats", 1),
            )
        return flights


class FlightDetail(generics.RetrieveAPIView):
    serializer_class = FlightSerializer
    queryset = Flight.objects.all()


class FlightLive(APIView):
    def get(self, request, pk):
        return Response(flight_status(get_object_or_404(Flight, pk=pk)))


class Bookings(viewsets.ReadOnlyModelViewSet):
    serializer_class = BookingSerializer

    def get_queryset(self):
        return Booking.objects.filter(user=self.request.user).select_related("flight").prefetch_related("food_orders__items")

    def create(self, request):
        payload = BookingInput(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        request_id = data.get("request_id") or uuid.uuid4()
        fingerprint = {field: data[field] for field in ("flight_id", "seats", "adults", "children", "infants", "payment", "meals")}
        with transaction.atomic():
            user = get_object_or_404(User.objects.select_for_update(), pk=request.user.pk)
            if not eligible(user):
                raise PermissionDenied("This account cannot make bookings.")
            existing = self.get_queryset().filter(request_id=request_id).first()
            if existing:
                if ((existing.request_payload and existing.request_payload != fingerprint)
                        or (not existing.request_payload and (existing.flight_id != data["flight_id"] or existing.seats != data["seats"]
                        or any(getattr(existing, field) != data[field] for field in ("adults", "children", "infants"))
                        or data["meals"] or data["payment"] != "success"))):
                    raise Conflict("This request ID was previously used for a different booking.")
                return Response(self.get_serializer(existing).data)
            flight = get_object_or_404(Flight.objects.select_for_update(), pk=data["flight_id"])
            seats = data["seats"]
            if flight.departure <= timezone.now() or flight.status not in {Flight.Status.ON_TIME, Flight.Status.DELAYED}:
                raise Conflict("This flight is closed for bookings.")
            if flight.seats_available < seats:
                raise Conflict("There are no longer enough seats available.")
            simulate_payment(data["payment"])
            booking = Booking.objects.create(
                user=request.user, flight=flight, seats=seats, unit_price=flight.price, request_id=request_id,
                adults=data["adults"], children=data["children"], infants=data["infants"],
                request_payload=fingerprint,
            )
            flight.seats_available -= seats
            flight.save(update_fields=["seats_available"])
            if data["meals"]:
                booking.flight = flight
                purchase_food(booking, data["meals"], request_id, payment=data["payment"])
        return Response(self.get_serializer(booking).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        found = self.get_object()
        with transaction.atomic():
            flight = Flight.objects.select_for_update().get(pk=found.flight_id)
            booking = Booking.objects.select_for_update().get(pk=found.pk)
            if booking.status == Booking.Status.CONFIRMED:
                payload = CancellationInput(data=request.data)
                payload.is_valid(raise_exception=True)
                if flight.status == Flight.Status.DEPARTED or flight.status == Flight.Status.LANDED:
                    raise Conflict("This flight has already departed.")
                if flight.departure <= timezone.now() and flight.status != Flight.Status.CANCELLED:
                    raise Conflict("Trips can be cancelled before scheduled departure.")
                booking.status = Booking.Status.CANCELLED
                booking.payment_status = Booking.Payment.REFUNDED
                booking.cancelled_at = timezone.now()
                booking.cancellation_reason = payload.validated_data["reason"]
                booking.save(update_fields=["status", "payment_status", "cancelled_at", "cancellation_reason"])
                refund_food_orders(booking.food_orders.all(), "Flight booking cancelled")
                flight.seats_available += booking.seats
                flight.save(update_fields=["seats_available"])
            booking.flight = flight
        return Response(self.get_serializer(booking).data)


class AdminUsers(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = UserSerializer
    queryset = User.objects.order_by("-date_joined")

    @action(detail=False, methods=["get"])
    def pending(self, request):
        pending = self.get_queryset().filter(approval_status=User.Approval.PENDING, is_staff=False)
        return Response(self.get_serializer(pending, many=True).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self.change_approval(User.Approval.APPROVED)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self.change_approval(User.Approval.REJECTED)

    def change_approval(self, next_status):
        user_id = self.get_object().pk
        with transaction.atomic():
            user = get_object_or_404(User.objects.select_for_update(), pk=user_id)
            if user.is_staff or user.is_superuser:
                raise Conflict("Administrator accounts cannot be managed through this endpoint.")
            if user.approval_status != next_status:
                user.approval_status = next_status
                user.save(update_fields=["approval_status"])
                if next_status == User.Approval.APPROVED:
                    def notify():
                        try:
                            send_approval_email.delay(user.pk)
                        except Exception:
                            logger.exception("Could not submit approval email task for user %s", user.pk)
                    transaction.on_commit(notify)
        return Response(self.get_serializer(user).data)


class AdminFlights(viewsets.ModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = FlightSerializer
    queryset = Flight.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action in {"update", "partial_update", "destroy", "set_status"}:
            return queryset.select_for_update()
        return queryset

    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                return super().create(request, *args, **kwargs)
        except IntegrityError as exc:
            raise Conflict("This flight and departure already exist.") from exc

    def update(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                return super().update(request, *args, **kwargs)
        except IntegrityError as exc:
            raise Conflict("This flight and departure already exist.") from exc

    def destroy(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                return super().destroy(request, *args, **kwargs)
        except ProtectedError as exc:
            raise Conflict("Flights with booking history cannot be deleted.") from exc

    @action(detail=True, methods=["put"], url_path="status")
    def set_status(self, request, pk=None):
        payload = serializers.Serializer()
        payload.fields["status"] = serializers.ChoiceField(choices=Flight.Status)
        values = payload.run_validation(request.data)
        with transaction.atomic():
            flight = self.get_object()
            flight.status = values["status"]
            flight.status_updated_at = timezone.now()
            if flight.status == Flight.Status.CANCELLED:
                flight.food_ordering_open = False
                refund_food_orders(FoodOrder.objects.filter(booking__flight=flight), "Flight cancelled by administrator")
            flight.save(update_fields=["status", "status_updated_at", "food_ordering_open"])
        return Response(self.get_serializer(flight).data)


class AdminStats(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        confirmed = Booking.objects.filter(status=Booking.Status.CONFIRMED)
        return Response({
            "pending_users": User.objects.filter(approval_status=User.Approval.PENDING, is_staff=False).count(),
            "flights": Flight.objects.count(),
            "confirmed_bookings": confirmed.count(),
            "confirmed_seats": confirmed.aggregate(total=Sum("seats", default=0))["total"],
        })

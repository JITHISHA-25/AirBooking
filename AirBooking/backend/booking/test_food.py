import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from .models import Booking, Flight, FlightMeal, FoodOrder, FoodOrderItem, Meal, User


def fixtures():
    user = User.objects.create_user("food-owner", "food-owner@example.test", approval_status="approved")
    departure = timezone.now() + timedelta(days=1)
    flight = Flight.objects.create(number="AI501", airline="Example Air", origin="COK", destination="BLR",
        departure=departure, arrival=departure + timedelta(hours=1), price="1000.10", capacity=9, seats_available=7)
    booking = Booking.objects.create(user=user, flight=flight, seats=2, adults=2, unit_price=flight.price, request_id=uuid.uuid4())
    meal = Meal.objects.create(name="Vegetable rice", category="vegetarian", price="123.45", ingredient_notes="Contains dairy")
    second = Meal.objects.create(name="Chicken rice", category="non_vegetarian", price="200.25")
    FlightMeal.objects.create(flight=flight, meal=meal)
    FlightMeal.objects.create(flight=flight, meal=second)
    return user, flight, booking, meal, second


@override_settings(FOOD_ORDER_CUTOFF_HOURS=2, AIRLABS_API_KEY="")
class FoodTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user, self.flight, self.booking, self.meal, self.second = fixtures()
        self.admin = User.objects.create_user("food-admin", "food-admin@example.test", is_staff=True)
        self.client.force_authenticate(self.user)
        self.path = f"/api/bookings/{self.booking.pk}/food-orders/"

    def payload(self, quantity=1, **extra):
        return {"items": [{"meal_id": self.meal.pk, "quantity": quantity}], "request_id": str(uuid.uuid4()), **extra}

    def order(self, payload=None):
        response = self.client.post(self.path, payload or self.payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response

    def cancel(self, order_id):
        return self.client.post(self.path + f"{order_id}/cancel/", {}, format="json")

    def test_server_totals_and_maximum_across_all_items(self):
        payload = self.payload()
        payload["items"].append({"meal_id": self.second.pk, "quantity": 1, "unit_price": "0.01"})
        payload["total"] = "0.01"
        response = self.order(payload)
        self.assertEqual(response.data["total"], "323.70")
        self.assertEqual(response.data["items"][0]["unit_price"], "123.45")
        self.assertEqual(response.data["items"][1]["unit_price"], "200.25")
        trip = self.client.get(f"/api/bookings/{self.booking.pk}/").data
        self.assertEqual(trip["total"], "2000.20")
        self.assertEqual(trip["food_total"], "323.70")
        self.assertEqual(trip["combined_total"], "2323.90")
        self.cancel(response.data["id"])
        payload = self.payload(2)
        payload["items"].append({"meal_id": self.second.pk, "quantity": 1})
        self.assertEqual(self.client.post(self.path, payload, format="json").status_code, 400)

    def test_invalid_quantities_duplicates_and_empty_selection(self):
        for quantity in [0, -1, 3, 10, 1.5]:
            self.assertEqual(self.client.post(self.path, self.payload(quantity), format="json").status_code, 400)
        for items in [[], [{"meal_id": self.meal.pk, "quantity": 1}] * 2]:
            self.assertEqual(self.client.post(self.path, self.payload(items=items), format="json").status_code, 400)
        self.assertFalse(FoodOrder.objects.exists())

    def test_unassigned_and_inactive_meals_rejected(self):
        foreign = Meal.objects.create(name="Other flight only", category="vegetarian", price="100")
        other = Flight.objects.create(number="AI502", airline="Example", origin="COK", destination="DXB",
            departure=self.flight.departure, arrival=self.flight.arrival, price="1000", capacity=9, seats_available=9)
        FlightMeal.objects.create(flight=other, meal=foreign)
        payload = self.payload(items=[{"meal_id": foreign.pk, "quantity": 1}])
        self.assertEqual(self.client.post(self.path, payload, format="json").status_code, 400)
        self.meal.active = False
        self.meal.save()
        self.assertEqual(self.client.post(self.path, self.payload(), format="json").status_code, 400)
        menu = self.client.get(f"/api/flights/{self.flight.pk}/meals/")
        self.assertEqual([meal["id"] for meal in menu.data["meals"]], [self.second.pk])

    def test_owner_and_admin_permissions(self):
        created = self.order()
        other = User.objects.create_user("food-other", "food-other@example.test", approval_status="approved")
        for user, expected in [(None, 401), (other, 404), (self.admin, 404)]:
            client = APIClient()
            if user:
                client.force_authenticate(user)
            self.assertEqual(client.get(self.path).status_code, expected)
            self.assertEqual(client.post(self.path, self.payload(), format="json").status_code, expected)
            self.assertEqual(client.post(self.path + f"{created.data['id']}/cancel/").status_code, expected)
        for path in ["/api/admin/meals/", f"/api/admin/flights/{self.flight.pk}/food-orders/", f"/api/admin/flights/{self.flight.pk}/meals/"]:
            self.assertEqual(self.client.get(path).status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f"/api/admin/flights/{self.flight.pk}/food-orders/").status_code, 200)

    def test_cutoff_boundaries_and_configurable_hours(self):
        cutoff = self.flight.departure - timedelta(hours=2)
        with patch("booking.food.timezone.now", return_value=cutoff - timedelta(microseconds=1)):
            order = self.order()
        with patch("booking.food.timezone.now", return_value=cutoff):
            self.assertEqual(self.cancel(order.data["id"]).status_code, 409)
            self.assertFalse(self.client.get(f"/api/flights/{self.flight.pk}/meals/").data["available"])
        with patch("booking.food.timezone.now", return_value=cutoff - timedelta(microseconds=1)):
            self.assertEqual(self.cancel(order.data["id"]).status_code, 200)
        for stamp in [cutoff, cutoff + timedelta(seconds=1)]:
            with patch("booking.food.timezone.now", return_value=stamp):
                self.assertEqual(self.client.post(self.path, self.payload(), format="json").status_code, 409)
        with override_settings(FOOD_ORDER_CUTOFF_HOURS=26):
            self.assertEqual(self.client.post(self.path, self.payload(), format="json").status_code, 409)

    def test_idempotent_replay_conflicts_and_one_active_order(self):
        payload = self.payload()
        first = self.order(payload)
        self.assertEqual(self.client.post(self.path, payload, format="json").data, first.data)
        changed = {**payload, "items": [{"meal_id": self.meal.pk, "quantity": 2}]}
        self.assertEqual(self.client.post(self.path, changed, format="json").status_code, 409)
        self.assertEqual(self.client.post(self.path, {**payload, "payment": "decline"}, format="json").status_code, 409)
        self.assertEqual(self.client.post(self.path, self.payload(), format="json").status_code, 409)
        self.cancel(first.data["id"])
        replay = self.client.post(self.path, payload, format="json")
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.data["id"], first.data["id"])
        self.assertEqual(replay.data["payment_status"], "refunded")
        self.order()
        self.assertEqual(FoodOrder.objects.filter(status="active").count(), 1)

    def test_request_id_cannot_be_reused_on_another_booking(self):
        payload = self.payload()
        self.order(payload)
        another = Booking.objects.create(user=self.user, flight=self.flight, seats=1, unit_price="1000", request_id=uuid.uuid4())
        response = self.client.post(f"/api/bookings/{another.pk}/food-orders/", payload, format="json")
        self.assertEqual(response.status_code, 409)

    def test_existing_trip_decline_leaves_booking_and_inventory_unchanged(self):
        payload = self.payload(payment="decline")
        self.assertEqual(self.client.post(self.path, payload, format="json").status_code, 402)
        self.booking.refresh_from_db(); self.flight.refresh_from_db()
        self.assertEqual(self.booking.status, "confirmed")
        self.assertEqual(self.flight.seats_available, 7)
        self.assertFalse(FoodOrder.objects.exists())
        self.order({**payload, "payment": "success"})

    def test_preexisting_booking_history_and_catalog_edits(self):
        self.assertEqual(self.booking.request_payload, {})
        before = self.client.get(f"/api/bookings/{self.booking.pk}/").data
        self.assertEqual(before["food_orders"], [])
        self.assertEqual(before["food_total"], "0.00")
        order = self.order()
        self.client.force_authenticate(self.admin)
        response = self.client.patch(f"/api/admin/meals/{self.meal.pk}/", {"price": "999.99", "name": "New name", "active": False})
        self.assertEqual(response.status_code, 200)
        self.client.force_authenticate(self.user)
        historical = self.client.get(self.path).data[0]
        self.assertEqual(historical["items"][0]["purchased_name"], "Vegetable rice")
        self.assertEqual(historical["total"], "123.45")
        self.cancel(order.data["id"])
        self.assertEqual(self.client.post(self.path, self.payload(), format="json").status_code, 400)
        self.meal.refresh_from_db(); self.meal.active = True; self.meal.save()
        fresh = self.order()
        self.assertEqual(fresh.data["total"], "999.99")
        self.assertEqual(fresh.data["items"][0]["purchased_name"], "New name")

    def test_booking_cancellation_refunds_food_even_after_food_cutoff(self):
        order = self.order()
        with patch("booking.food.timezone.now", return_value=self.flight.departure - timedelta(hours=1)):
            response = self.client.post(f"/api/bookings/{self.booking.pk}/cancel/", {"reason": "Plans changed"})
        self.assertEqual(response.status_code, 200)
        food = FoodOrder.objects.get(pk=order.data["id"])
        self.assertEqual((food.status, food.payment_status), ("cancelled", "refunded"))
        self.assertIsNotNone(food.cancelled_at)
        self.assertIsNotNone(food.refunded_at)
        self.assertEqual(response.data["food_total"], "0.00")
        self.assertEqual(self.cancel(food.pk).status_code, 200)

    def test_admin_flight_cancellation_both_paths_refund_and_exclude_quantities(self):
        for method, path in [("put", f"/api/admin/flights/{self.flight.pk}/status/"), ("patch", f"/api/admin/flights/{self.flight.pk}/")]:
            self.client.force_authenticate(self.user)
            self.order()
            self.client.force_authenticate(self.admin)
            response = getattr(self.client, method)(path, {"status": "cancelled"}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.data["food_ordering_open"])
            self.assertEqual(FoodOrder.objects.filter(status="active").count(), 0)
            report = self.client.get(f"/api/admin/flights/{self.flight.pk}/food-orders/")
            self.assertEqual(report.data["requirements"], [])
            self.client.patch(f"/api/admin/flights/{self.flight.pk}/", {"status": "on_time", "food_ordering_open": True}, format="json")

    def test_admin_catalog_assignment_and_quantities(self):
        self.client.force_authenticate(self.admin)
        created = self.client.post("/api/admin/meals/", {"name": "Fruit", "category": "vegetarian", "price": "70.50"}, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.client.post("/api/admin/meals/", {"name": "Bad", "category": "vegetarian", "price": "-1"}).status_code, 400)
        assignment = f"/api/admin/flights/{self.flight.pk}/meals/"
        self.assertEqual(self.client.put(assignment, {"meal_ids": [created.data["id"]], "food_ordering_open": True}, format="json").status_code, 200)
        self.assertEqual(FlightMeal.objects.filter(flight=self.flight).count(), 1)
        self.assertEqual(self.client.put(assignment, {"meal_ids": [99999]}, format="json").status_code, 400)
        self.client.force_authenticate(self.user)
        order = self.order(self.payload(items=[{"meal_id": created.data["id"], "quantity": 2}]))
        self.client.force_authenticate(self.admin)
        path = f"/api/admin/flights/{self.flight.pk}/food-orders/"
        self.assertEqual(self.client.get(path).data["requirements"][0]["quantity"], 2)
        self.client.force_authenticate(self.user); self.cancel(order.data["id"])
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(path).data["requirements"], [])

    def test_closed_flight_states_and_booking_status(self):
        for state in ["cancelled", "departed", "landed"]:
            Flight.objects.filter(pk=self.flight.pk).update(status=state)
            self.assertEqual(self.client.post(self.path, self.payload(), format="json").status_code, 409)
        Flight.objects.filter(pk=self.flight.pk).update(status="on_time", food_ordering_open=False)
        self.assertEqual(self.client.post(self.path, self.payload(), format="json").status_code, 409)
        Flight.objects.filter(pk=self.flight.pk).update(food_ordering_open=True)
        Booking.objects.filter(pk=self.booking.pk).update(status="cancelled")
        self.assertEqual(self.client.post(self.path, self.payload(), format="json").status_code, 409)

    def test_initial_booking_food_atomic_success_and_replay(self):
        payload = {"flight_id": self.flight.pk, "seats": 2, "request_id": str(uuid.uuid4()),
                   "meals": [{"meal_id": self.meal.pk, "quantity": 2}]}
        response = self.client.post("/api/bookings/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["food_total"], "246.90")
        self.assertEqual(response.data["combined_total"], "2247.10")
        self.assertEqual(len(response.data["food_orders"]), 1)
        self.assertEqual(self.client.post("/api/bookings/", payload, format="json").data["id"], response.data["id"])
        self.assertEqual(self.client.post("/api/bookings/", {**payload, "meals": []}, format="json").status_code, 409)
        self.flight.refresh_from_db()
        self.assertEqual(self.flight.seats_available, 5)

    def test_initial_decline_and_invalid_meals_roll_back_inventory_and_booking(self):
        payload = {"flight_id": self.flight.pk, "seats": 2, "request_id": str(uuid.uuid4()),
                   "meals": [{"meal_id": self.meal.pk, "quantity": 2}], "payment": "decline"}
        self.assertEqual(self.client.post("/api/bookings/", payload, format="json").status_code, 402)
        payload.update(payment="success", meals=[{"meal_id": 99999, "quantity": 1}])
        self.assertEqual(self.client.post("/api/bookings/", payload, format="json").status_code, 400)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertFalse(FoodOrder.objects.exists())
        self.flight.refresh_from_db()
        self.assertEqual(self.flight.seats_available, 7)

    def test_booking_without_food_is_still_optional_after_food_cutoff(self):
        with patch("booking.food.timezone.now", return_value=self.flight.departure - timedelta(hours=1)):
            response = self.client.post("/api/bookings/", {"flight_id": self.flight.pk, "seats": 1,
                "request_id": str(uuid.uuid4())}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["food_orders"], [])
        self.assertEqual(response.data["food_total"], "0.00")

    def test_cutoff_rechecked_after_waiting_for_catalog_rows(self):
        cutoff = self.flight.departure - timedelta(hours=2)
        with patch("booking.food.timezone.now", side_effect=[cutoff - timedelta(microseconds=1), cutoff]):
            response = self.client.post(self.path, self.payload(), format="json")
        self.assertEqual(response.status_code, 409)
        self.assertFalse(FoodOrder.objects.exists())


@override_settings(FOOD_ORDER_CUTOFF_HOURS=2)
class FoodConcurrencyTests(TransactionTestCase):
    def test_simultaneous_orders_only_create_one_active_purchase(self):
        if connection.vendor == "sqlite" and "memory" in str(connection.settings_dict["NAME"]):
            self.skipTest("Use --settings=config.test_settings for file-backed SQLite transaction verification.")
        user, _, booking, meal, _ = fixtures()
        def buy(_):
            close_old_connections()
            try:
                client = APIClient(); client.force_authenticate(user)
                return client.post(f"/api/bookings/{booking.pk}/food-orders/", {"items": [{"meal_id": meal.pk, "quantity": 1}],
                    "request_id": str(uuid.uuid4())}, format="json").status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(buy, range(2)))
        self.assertEqual(sorted(statuses), [201, 409])
        self.assertEqual(FoodOrder.objects.filter(status="active").count(), 1)
        self.assertEqual(FoodOrderItem.objects.count(), 1)

import io
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import Resolver404, resolve
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import Complaint, Flight, User


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AirBookingTests(APITestCase):
    password = "Interval-Carry-Velvet-483"

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser("reviewer", "reviewer@example.test", self.password)
        self.traveler = User.objects.create_user(
            "traveler", "traveler@example.test", self.password, approval_status=User.Approval.APPROVED,
        )
        departure = timezone.now() + timedelta(days=1)
        self.flight = Flight.objects.create(
            number="AI501", airline="Example Air", origin="COK", destination="BLR", departure=departure,
            arrival=departure + timedelta(hours=1), price="1499.00", capacity=2, seats_available=2,
        )

    def login(self, username):
        self.client.credentials()
        return self.client.post("/api/auth/login/", {"username": username, "password": self.password})

    def use_token(self, access):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_removed_pickup_routes_are_not_available(self):
        for path in ("/api/pickup/retired-link/", "/api/bookings/1/pickup-link/"):
            with self.subTest(path=path), self.assertRaises(Resolver404):
                resolve(path)

    def test_complaint_submission_privacy_and_admin_viewer(self):
        self.assertEqual(self.client.get("/api/complaints/").status_code, 401)
        self.assertEqual(self.client.post("/api/complaints/", {"subject": "Issue", "message": "Help"}).status_code, 401)
        self.assertEqual(self.client.get("/api/admin/complaints/").status_code, 401)

        self.use_token(self.login("traveler").data["access"])
        created = self.client.post("/api/complaints/", {
            "subject": "Booking issue", "message": "My booking reference is missing.\nPlease help.",
            "user": self.admin.pk,
        })
        self.assertEqual(created.status_code, 201)
        complaint = Complaint.objects.get(pk=created.data["id"])
        self.assertEqual(complaint.user, self.traveler)
        self.assertEqual(created.data["message"], complaint.message)
        self.assertNotIn("email", created.data)
        self.assertEqual([item["id"] for item in self.client.get("/api/complaints/").data], [complaint.pk])
        detail = f"/api/complaints/{complaint.pk}/"
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual(self.client.patch(detail, {"subject": "Changed"}).status_code, 405)
        self.assertEqual(self.client.delete(detail).status_code, 405)
        self.assertEqual(self.client.get("/api/admin/complaints/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/admin/complaints/{complaint.pk}/").status_code, 403)

        other = User.objects.create_user(
            "another", "another@example.test", self.password, approval_status=User.Approval.APPROVED,
        )
        other_complaint = Complaint.objects.create(user=other, subject="Another issue", message="Details")
        self.assertEqual(self.client.get(f"/api/complaints/{other_complaint.pk}/").status_code, 404)
        self.use_token(self.login("another").data["access"])
        self.assertEqual(self.client.get(detail).status_code, 404)
        self.assertEqual([item["id"] for item in self.client.get("/api/complaints/").data], [other_complaint.pk])

        self.use_token(self.login("reviewer").data["access"])
        records = self.client.get("/api/admin/complaints/")
        self.assertEqual(records.status_code, 200)
        self.assertEqual([item["id"] for item in records.data], [other_complaint.pk, complaint.pk])
        self.assertEqual(records.data[1]["username"], self.traveler.username)
        self.assertEqual(records.data[1]["email"], self.traveler.email)
        admin_detail = f"/api/admin/complaints/{complaint.pk}/"
        self.assertEqual(self.client.get(admin_detail).data["message"], complaint.message)
        self.assertEqual(self.client.patch(admin_detail, {"subject": "Changed"}).status_code, 405)
        self.assertEqual(self.client.delete(admin_detail).status_code, 405)
        self.assertEqual(self.client.post("/api/admin/complaints/", {"subject": "Issue", "message": "Help"}).status_code, 405)

    def test_complaint_validation(self):
        self.use_token(self.login("traveler").data["access"])
        for payload in (
            {}, {"subject": "   ", "message": "Details"}, {"subject": "Issue", "message": "\n "},
            {"subject": "x" * 161, "message": "Details"}, {"subject": "Issue", "message": "x" * 5001},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post("/api/complaints/", payload).status_code, 400)
        self.assertEqual(Complaint.objects.count(), 0)

    def test_cabin_class_inventory_and_search(self):
        self.use_token(self.login("reviewer").data["access"])
        for index, cabin in enumerate(("premium_economy", "business", "first")):
            created = self.client.post("/api/admin/flights/", {
                "number": f"AI60{index}", "airline": "Example Air", "origin": "COK", "destination": "BLR",
                "departure": self.flight.departure.isoformat(), "arrival": self.flight.arrival.isoformat(),
                "price": "4500.00", "capacity": 9, "cabin_class": cabin,
            })
            self.assertEqual(created.status_code, 201)
            self.assertEqual(created.data["cabin_class"], cabin)
        self.assertEqual(self.client.patch(f"/api/admin/flights/{self.flight.pk}/", {"cabin_class": "unknown"}).status_code, 400)
        self.use_token(self.login("traveler").data["access"])
        economy = self.client.get("/api/flights/search/", {"cabin_class": "economy"})
        self.assertEqual([flight["id"] for flight in economy.data], [self.flight.pk])
        for cabin in ("premium_economy", "business", "first"):
            found = self.client.get("/api/flights/search/", {"cabin_class": cabin, "adults": 2, "children": 1, "infants": 1})
            self.assertEqual(found.status_code, 200)
            self.assertEqual([flight["cabin_class"] for flight in found.data], [cabin])
        self.assertEqual(self.client.get("/api/flights/search/", {"cabin_class": "unknown"}).status_code, 400)
        self.assertEqual(self.client.get("/api/flights/search/", {"cabin_class": "economy", "adults": 3}).data, [])

    def test_traveller_counts_booking_retries_and_cancellation(self):
        self.flight.capacity = self.flight.seats_available = 9
        self.flight.save()
        self.use_token(self.login("traveler").data["access"])
        payload = {"flight_id": self.flight.pk, "adults": 2, "children": 1, "infants": 1, "request_id": str(uuid.uuid4())}
        booked = self.client.post("/api/bookings/", payload)
        self.assertEqual(booked.status_code, 201)
        for field, expected in (("adults", 2), ("children", 1), ("infants", 1), ("seats", 4), ("total", "5996.00")):
            self.assertEqual(booked.data[field], expected)
        self.flight.refresh_from_db()
        self.assertEqual(self.flight.seats_available, 5)
        self.assertEqual(self.client.post("/api/bookings/", payload).status_code, 200)
        self.assertEqual(self.client.post("/api/bookings/", {**payload, "adults": 3, "children": 0}).status_code, 409)
        self.assertEqual(self.client.get("/api/bookings/").data[0]["infants"], 1)
        self.use_token(self.login("reviewer").data["access"])
        self.assertEqual(self.client.patch(f"/api/admin/flights/{self.flight.pk}/", {"cabin_class": "business"}).status_code, 400)
        self.use_token(self.login("traveler").data["access"])
        self.assertEqual(self.client.post(f"/api/bookings/{booked.data['id']}/cancel/", {"reason": "Change of travel plans"}).status_code, 200)
        self.flight.refresh_from_db()
        self.assertEqual(self.flight.seats_available, 9)

    def test_traveller_validation_in_search_and_booking(self):
        self.use_token(self.login("traveler").data["access"])
        for party in (
            {"adults": 0}, {"adults": -1}, {"children": 7}, {"infants": 2},
            {"adults": 5, "children": 5}, {"adults": 2, "seats": 1}, {"adults": "two"},
            {"adults": 1, "children": -1}, {"infants": 7},
        ):
            with self.subTest(party=party):
                self.assertEqual(self.client.get("/api/flights/search/", party).status_code, 400)
                self.assertEqual(self.client.post("/api/bookings/", {"flight_id": self.flight.pk, **party}).status_code, 400)

    def test_registration_approval_email_and_jwt_revocation(self):
        registration = self.client.post("/api/auth/register/", {
            "username": "applicant", "email": "Applicant@example.test", "password": self.password,
        })
        self.assertEqual(registration.status_code, 201)
        self.assertEqual(registration.data["approval_status"], "pending")
        self.assertNotIn("password", registration.data)
        self.assertEqual(self.login("applicant").status_code, 403)
        self.assertEqual(self.client.get("/api/flights/search/").status_code, 401)

        endpoint = f"/api/admin/users/{registration.data['id']}/"
        self.use_token(self.login("reviewer").data["access"])
        pending = self.client.get("/api/admin/users/pending/")
        self.assertEqual([user["username"] for user in pending.data], ["applicant"])
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(endpoint + "approve/").status_code, 200)
            self.assertEqual(self.client.post(endpoint + "approve/").status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["applicant@example.test"])

        session = self.login("applicant").data
        refreshed = self.client.post("/api/auth/token/refresh/", {"refresh": session["refresh"]})
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(self.client.post("/api/auth/token/refresh/", {"refresh": session["refresh"]}).status_code, 401)
        self.use_token(refreshed.data["access"])
        self.assertEqual(self.client.get("/api/auth/me/").data["username"], "applicant")
        self.assertEqual(self.client.get("/api/admin/users/pending/").status_code, 403)

        self.use_token(self.login("reviewer").data["access"])
        self.assertEqual(self.client.post(endpoint + "reject/").status_code, 200)
        self.use_token(refreshed.data["access"])
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/token/refresh/", {"refresh": refreshed.data["refresh"]}).status_code, 403)

    def test_search_payment_inventory_and_idempotent_cancellation(self):
        self.use_token(self.login("traveler").data["access"])
        search = self.client.get("/api/flights/search/", {
            "origin": "cok", "destination": "blr",
            "date": timezone.localtime(self.flight.departure).date().isoformat(), "seats": 2,
        })
        self.assertEqual([flight["id"] for flight in search.data], [self.flight.id])
        self.assertEqual(self.client.get("/api/flights/search/", {"airport": "CCJ"}).data, [])
        self.assertEqual(self.client.get("/api/flights/search/", {"seats": 3}).data, [])
        self.assertEqual(self.client.get("/api/flights/search/", {"date": "yesterday"}).status_code, 400)

        payload = {"flight_id": self.flight.id, "seats": 2, "request_id": str(uuid.uuid4())}
        self.assertEqual(self.client.post("/api/bookings/", {**payload, "payment": "decline"}).status_code, 402)
        self.flight.refresh_from_db()
        self.assertEqual(self.flight.seats_available, 2)
        booked = self.client.post("/api/bookings/", payload)
        self.assertEqual(booked.status_code, 201)
        self.assertEqual(booked.data["total"], "2998.00")
        replay = self.client.post("/api/bookings/", payload)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.data["reference"], booked.data["reference"])
        self.assertEqual(self.client.post("/api/bookings/", {**payload, "seats": 1}).status_code, 409)
        self.assertEqual(self.client.post("/api/bookings/", {**payload, "request_id": str(uuid.uuid4())}).status_code, 409)
        self.flight.refresh_from_db()
        self.assertEqual(self.flight.seats_available, 0)

        detail = f"/api/bookings/{booked.data['id']}/"
        self.use_token(self.login("reviewer").data["access"])
        self.assertEqual(self.client.get(detail).status_code, 404)
        self.assertEqual(self.client.post(detail + "cancel/").status_code, 404)
        self.use_token(self.login("traveler").data["access"])
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual(len(self.client.get("/api/bookings/").data), 1)
        for _ in range(2):
            self.assertEqual(self.client.post(detail + "cancel/", {"reason": "Change of travel plans"}).data["payment_status"], "refunded")
        self.flight.refresh_from_db()
        self.assertEqual(self.flight.seats_available, 2)

    def test_admin_flight_management_and_status(self):
        self.use_token(self.login("traveler").data["access"])
        self.client.post("/api/bookings/", {"flight_id": self.flight.id, "seats": 2})
        self.assertEqual(self.client.get("/api/admin/stats/").status_code, 403)

        self.use_token(self.login("reviewer").data["access"])
        flight_url = f"/api/admin/flights/{self.flight.id}/"
        self.assertEqual(self.client.patch(flight_url, {"capacity": 1}).status_code, 400)
        changed = self.client.patch(flight_url, {"capacity": 3})
        self.assertEqual(changed.data["seats_available"], 1)
        self.assertEqual(self.client.delete(flight_url).status_code, 409)
        result = self.client.put(flight_url + "status/", {"status": "delayed"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["status"], "delayed")
        self.assertEqual(self.client.put(flight_url + "status/", {"status": "bad"}).status_code, 400)
        self.assertEqual(self.client.get(f"/api/flights/{self.flight.id}/status/").data["status"], "delayed")
        self.assertEqual(self.client.get("/api/admin/stats/").data["confirmed_seats"], 2)

        new = self.client.post("/api/admin/flights/", {
            "number": "AI502", "airline": "Example Air", "origin": "COK", "destination": "BOM",
            "departure": self.flight.departure.isoformat(), "arrival": self.flight.arrival.isoformat(),
            "price": "2800.50", "capacity": 100,
        })
        self.assertEqual(new.status_code, 201)
        self.assertEqual(new.data["seats_available"], 100)
        self.assertEqual(self.client.delete(f"/api/admin/flights/{new.data['id']}/").status_code, 204)

    def test_cancellation_requires_and_preserves_reason(self):
        self.use_token(self.login("traveler").data["access"])
        booked = self.client.post("/api/bookings/", {"flight_id": self.flight.pk, "seats": 1})
        endpoint = f"/api/bookings/{booked.data['id']}/cancel/"
        for payload in ({}, {"reason": ""}, {"reason": "  \n "}, {"reason": "x" * 501}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post(endpoint, payload).status_code, 400)
        self.flight.refresh_from_db()
        self.assertEqual(self.flight.seats_available, 1)
        self.assertEqual(self.client.get("/api/bookings/").data[0]["status"], "confirmed")
        cancelled = self.client.post(endpoint, {"reason": "  My meeting was rescheduled.  "})
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.data["cancellation_reason"], "My meeting was rescheduled.")
        self.assertEqual(cancelled.data["payment_status"], "refunded")
        self.assertEqual(self.client.get("/api/bookings/").data[0]["cancellation_reason"], "My meeting was rescheduled.")
        for payload in ({}, {"reason": "A different reason"}):
            replay = self.client.post(endpoint, payload)
            self.assertEqual(replay.status_code, 200)
            self.assertEqual(replay.data["cancellation_reason"], "My meeting was rescheduled.")
        self.flight.refresh_from_db()
        self.assertEqual(self.flight.seats_available, 2)

    @override_settings(AIRLABS_API_KEY="fixture")
    @patch("booking.live.urlopen")
    def test_airlabs_status_requires_matching_flight_instance_and_is_cached(self, open_url):
        self.use_token(self.login("traveler").data["access"])
        payload = {"response": {
            "flight_iata": self.flight.number, "dep_iata": self.flight.origin, "arr_iata": self.flight.destination,
            "status": "active", "dep_time_ts": int(self.flight.departure.timestamp()) - 86400,
        }}
        endpoint = f"/api/flights/{self.flight.id}/status/"

        def reply():
            return io.BytesIO(json.dumps(payload).encode())

        open_url.side_effect = lambda *args, **kwargs: reply()
        self.assertEqual(self.client.get(endpoint).data["source"], "airbooking")
        cache.clear()
        payload["response"]["dep_time_ts"] = int(self.flight.departure.timestamp())
        for _ in range(2):
            status = self.client.get(endpoint)
            self.assertEqual(status.data["source"], "airlabs")
            self.assertEqual(status.data["status"], "departed")
        self.assertEqual(open_url.call_count, 2)

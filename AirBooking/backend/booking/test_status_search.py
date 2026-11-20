import io
import json
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from .models import Booking, Flight, User


@override_settings(AIRLABS_API_KEY="test-provider-key")
class FlightStatusSearchTests(APITestCase):
    endpoint = "/api/flights/status/search/"

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("status-user", "status@example.test", approval_status="approved")
        self.client.force_authenticate(self.user)
        clock = patch("booking.status_search.timezone.now", return_value=datetime(2026, 11, 20, 5, tzinfo=timezone.utc))
        clock.start()
        self.addCleanup(clock.stop)
        provider = patch("booking.status_search.urlopen")
        self.provider = provider.start()
        self.addCleanup(provider.stop)
        self.respond([])

    def row(self, **updates):
        return {"flight_iata": "6E2009", "airline_iata": "6E", "dep_iata": "DEL", "arr_iata": "BLR",
                "dep_time": "2026-11-20 12:00", "arr_time": "2026-11-20 14:30", "status": "scheduled", **updates}

    def respond(self, rows, **extra):
        self.provider.side_effect = lambda *args, **kwargs: io.BytesIO(json.dumps({"response": rows, **extra}).encode())

    def query(self, **updates):
        return self.client.get(self.endpoint, {"mode": "airport", "airport": "DEL", "direction": "departures", "date": "2026-11-20", **updates})

    def local_flight(self, demo=False, **updates):
        return Flight.objects.create(number="6E2009", airline="Local Air", origin="DEL", destination="BLR",
            departure=datetime(2026, 11, 20, 6, 30, tzinfo=timezone.utc),
            arrival=datetime(2026, 11, 20, 9, tzinfo=timezone.utc),
            price="4500", capacity=10, seats_available=10, demo=demo, **updates)

    def test_del_departures_to_blr_exclude_other_routes_and_days(self):
        flight = self.local_flight()
        self.respond([self.row(arr_iata="BOM"), self.row(dep_time="2026-11-19 12:00"),
                      self.row(flight_iata="AI502", dep_time="2026-11-20 13:00"),
                      self.row(dep_estimated="2026-11-20 12:20", dep_actual="2026-11-20 12:25",
                               dep_terminal="3", dep_gate="22", arr_baggage="6", dep_delayed=25)])
        result = self.query(destination="blr", airport="del")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["state"], "ok")
        self.assertEqual([row["number"] for row in result.data["results"]], ["6E2009", "AI502"])
        row = result.data["results"][0]
        self.assertEqual(row["status"], "delayed")
        self.assertEqual(row["dep"]["actual"], "2026-11-20 12:25")
        self.assertEqual(row["dep"]["gate"], "22")
        self.assertEqual(row["baggage"], "6")
        self.assertEqual(row["source"], "AirLabs")
        params = parse_qs(urlparse(self.provider.call_args.args[0]).query)
        self.assertEqual(params["dep_iata"], ["DEL"])
        self.assertEqual(self.provider.call_args.kwargs["timeout"], 4)
        self.assertEqual(Flight.objects.count(), 1)
        self.assertEqual(Booking.objects.count(), 0)
        flight.refresh_from_db()
        self.assertEqual(flight.seats_available, 10)
        self.assertNotIn("test-provider-key", json.dumps(result.data))

    def test_arrivals_include_overnight_flight_and_sort_by_arrival(self):
        self.respond([self.row(flight_iata="AI502", dep_time="2026-11-20 10:00", arr_time="2026-11-20 12:00"),
                      self.row(dep_time="2026-11-19 23:00", arr_time="2026-11-20 01:30"),
                      self.row(arr_time="2026-11-21 01:30")])
        result = self.query(airport="BLR", direction="arrivals", origin="DEL")
        self.assertEqual([row["number"] for row in result.data["results"]], ["6E2009", "AI502"])
        self.assertIn("arr_iata=BLR", self.provider.call_args.args[0])

    def test_route_and_flight_number_match_correct_instance(self):
        self.respond([self.row(dep_time="2026-11-19 12:00"), self.row(), self.row(flight_iata="AI502")])
        result = self.query(mode="flight_number", flight_number="6e 2009")
        self.assertEqual(len(result.data["results"]), 1)
        self.assertEqual(result.data["results"][0]["dep"]["scheduled"], "2026-11-20 12:00")
        self.assertIn("/schedules?", self.provider.call_args.args[0])
        self.assertIn("flight_iata=6E2009", self.provider.call_args.args[0])
        self.respond([self.row(), self.row(arr_iata="BOM"), self.row(dep_iata="BOM")])
        route = self.query(mode="route", origin="DEL", destination="BLR")
        self.assertEqual(len(route.data["results"]), 1)

    @override_settings(AIRLABS_API_KEY="")
    def test_missing_credentials_local_demo_and_unavailable(self):
        missing = self.query(destination="BLR")
        self.assertEqual(missing.data["state"], "unavailable")
        self.assertEqual(missing.data["results"], [])
        cache.clear()
        self.local_flight(demo=True)
        fallback = self.query(destination="BLR")
        self.assertEqual(fallback.data["state"], "fallback")
        self.assertEqual(fallback.data["results"][0]["source"], "Demo")
        self.assertEqual(fallback.data["results"][0]["dep"]["scheduled"], "2026-11-20 12:00")
        self.provider.assert_not_called()

    def test_timeout_falls_back_and_does_not_look_empty(self):
        self.provider.side_effect = TimeoutError("fixture timeout")
        result = self.query()
        self.assertEqual(result.data["state"], "unavailable")
        cache.clear()
        self.local_flight()
        result = self.query()
        self.assertEqual(result.data["state"], "fallback")
        self.assertEqual(result.data["results"][0]["source"], "AirBooking")

    def test_empty_outside_coverage_and_provider_error_are_distinct(self):
        self.assertEqual(self.query().data["state"], "empty")
        self.assertEqual(self.query(date="2026-12-20").data["state"], "outside_coverage")
        cache.clear()
        self.provider.side_effect = lambda *args, **kwargs: io.BytesIO(b'{"error":{"code":"api_key"}}')
        self.assertEqual(self.query().data["state"], "unavailable")

    def test_pagination_bound_cache_and_partial_failure(self):
        self.respond([self.row()], request={"has_more": True})
        result = self.query()
        self.assertTrue(result.data["partial"])
        self.assertEqual(self.provider.call_count, 3)
        self.assertEqual(len(result.data["results"]), 1)
        self.query()
        self.assertEqual(self.provider.call_count, 3)
        cache.clear()
        self.provider.side_effect = [io.BytesIO(json.dumps({"response": [self.row()], "request": {"has_more": True}}).encode()), URLError("fixture")]
        partial = self.query()
        self.assertEqual(partial.data["state"], "ok")
        self.assertTrue(partial.data["partial"])

    def test_status_mapping_and_utc_conversion_to_airport_date(self):
        row = self.row(status="unrecognized", dep_time=None, dep_time_utc="2026-11-19 20:00")
        self.respond([row])
        result = self.query()
        self.assertEqual(result.data["results"][0]["dep"]["scheduled"], "2026-11-20 01:30")
        self.assertEqual(result.data["results"][0]["status"], "unknown")

    @override_settings(AIRLABS_API_KEY="")
    def test_local_arrival_date_uses_airport_timezone(self):
        flight = self.local_flight()
        flight.departure = datetime(2026, 11, 19, 18, tzinfo=timezone.utc)
        flight.arrival = datetime(2026, 11, 19, 20, tzinfo=timezone.utc)
        flight.save()
        result = self.query(airport="BLR", direction="arrivals")
        self.assertEqual(result.data["results"][0]["arr"]["scheduled"], "2026-11-20 01:30")

    def test_validation_authentication_and_read_only(self):
        for params in ({}, {"mode": "route", "date": "2026-11-20"}, {"mode": "airport", "airport": "D1L", "date": "2026-11-20"},
                       {"mode": "flight_number", "flight_number": "bad", "date": "2026-11-20"},
                       {"mode": "route", "origin": "DEL", "destination": "DEL", "date": "2026-11-20"}):
            self.assertEqual(self.client.get(self.endpoint, params).status_code, 400)
        self.assertEqual(self.query(date="not-a-date").status_code, 400)
        self.assertEqual(self.client.post(self.endpoint, {}).status_code, 405)
        self.assertEqual(APIClient().get(self.endpoint).status_code, 401)
        self.provider.assert_not_called()

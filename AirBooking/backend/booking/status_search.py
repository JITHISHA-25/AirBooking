"""Read-only schedule searches. This module never writes Flight or Booking records."""
import hashlib
import json
from datetime import datetime, time, timedelta, timezone as dt_timezone
from functools import lru_cache
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Flight
from .live import provider_status

PAGE_SIZE = 50
MAX_PAGES = 3
MAX_LOCAL = 150


@lru_cache(maxsize=1)
def airport_zones():
    return airportsdata.load("IATA")


def zone(airport):
    name = airport_zones().get(airport, {}).get("tz")
    try:
        return ZoneInfo(name) if name else None
    except ZoneInfoNotFoundError:
        return None


def local_stamp(value, airport):
    local_zone = zone(airport)
    return value.astimezone(local_zone).strftime("%Y-%m-%d %H:%M") if local_zone else None


def provider_stamp(data, field, airport):
    # AirLabs' unsuffixed schedule fields are explicitly airport-local.
    value = data.get(field)
    if isinstance(value, str):
        try:
            parsed = parse_datetime(value)
        except ValueError:
            parsed = None
        if parsed is not None:
            if timezone.is_aware(parsed):
                return local_stamp(parsed, airport)
            return parsed.strftime("%Y-%m-%d %H:%M")
    try:
        stamp = data.get(field + "_ts")
        if stamp is not None:
            return local_stamp(datetime.fromtimestamp(float(stamp), tz=dt_timezone.utc), airport)
        utc = data.get(field + "_utc")
        parsed = parse_datetime(utc) if isinstance(utc, str) else None
        if parsed:
            if timezone.is_naive(parsed):
                parsed = parsed.replace(tzinfo=dt_timezone.utc)
            return local_stamp(parsed, airport)
    except (ValueError, TypeError, OverflowError, OSError):
        pass
    return None


def delay(value):
    try:
        return max(0, int(value)) if value is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def text_field(value):
    return str(value) if isinstance(value, (str, int, float)) else None


def normalize(data):
    origin, destination = data.get("dep_iata"), data.get("arr_iata")
    number = data.get("flight_iata")
    if not all(isinstance(value, str) and value for value in (origin, destination, number)):
        return None
    departure_delay, arrival_delay = delay(data.get("dep_delayed")), delay(data.get("arr_delayed"))
    mapped = provider_status(str(data.get("status")), departure_delay or 0)
    record = {"number": number.upper().replace(" ", ""), "airline": text_field(data.get("airline_name") or data.get("airline_iata") or data.get("airline_icao")),
              "origin": origin.upper(), "destination": destination.upper(), "status": mapped, "source": "AirLabs"}
    for prefix, airport in (("dep", origin), ("arr", destination)):
        record[prefix] = {"scheduled": provider_stamp(data, prefix + "_time", airport),
                          "estimated": provider_stamp(data, prefix + "_estimated", airport),
                          "actual": provider_stamp(data, prefix + "_actual", airport),
                          "terminal": text_field(data.get(prefix + "_terminal")), "gate": text_field(data.get(prefix + "_gate")),
                          "delay_minutes": departure_delay if prefix == "dep" else arrival_delay}
    record["baggage"] = text_field(data.get("arr_baggage"))
    return record


def matches(record, query):
    mode = query["mode"]
    side = "arr" if mode == "airport" and query["direction"] == "arrivals" else "dep"
    stamp = record[side]["scheduled"]
    if not stamp or stamp[:10] != query["date"].isoformat():
        return False
    if mode == "flight_number":
        return record["number"] == query["flight_number"]
    if mode == "route":
        return record["origin"] == query["origin"] and record["destination"] == query["destination"]
    if side == "dep":
        return record["origin"] == query["airport"] and (not query.get("destination") or record["destination"] == query["destination"])
    return record["destination"] == query["airport"] and (not query.get("origin") or record["origin"] == query["origin"])


def outside_window(query):
    airport = query.get("airport") if query["mode"] == "airport" else query.get("origin") if query["mode"] == "route" else None
    airport_zone = zone(airport) if airport else None
    now = timezone.now()
    if airport_zone:
        start = datetime.combine(query["date"], time.min, tzinfo=airport_zone)
        end = datetime.combine(query["date"] + timedelta(days=1), time.min, tzinfo=airport_zone)
        return end <= now or start > now + timedelta(hours=10)
    # Unknown timezone/flight-number search: only reject dates certainly outside
    # the window in every airport timezone, never assume the app's timezone.
    return query["date"] < (now - timedelta(hours=12)).date() or query["date"] > (now + timedelta(hours=24)).date()


def local_records(query):
    flights = Flight.objects.all()
    if query["mode"] == "flight_number":
        flights = flights.filter(number=query["flight_number"])
    elif query["mode"] == "route":
        flights = flights.filter(origin=query["origin"], destination=query["destination"])
    elif query["direction"] == "arrivals":
        flights = flights.filter(destination=query["airport"])
        if query.get("origin"):
            flights = flights.filter(origin=query["origin"])
    else:
        flights = flights.filter(origin=query["airport"])
        if query.get("destination"):
            flights = flights.filter(destination=query["destination"])
    # A broad UTC band covers all airport-local dates, including overnight arrivals.
    side = "arrival" if query["mode"] == "airport" and query["direction"] == "arrivals" else "departure"
    start = datetime.combine(query["date"], time.min, tzinfo=dt_timezone.utc) - timedelta(hours=14)
    end = start + timedelta(days=2, hours=2)
    flights = flights.filter(**{side + "__gte": start, side + "__lt": end}).order_by(side, "id")
    found = []
    incomplete = False
    for index, flight in enumerate(flights[:601]):
        if index == 600:
            return found, True
        record = {"number": flight.number, "airline": flight.airline, "origin": flight.origin, "destination": flight.destination,
                  "status": flight.status, "source": "Demo" if flight.demo else "AirBooking", "baggage": None}
        for prefix, airport, stamp in (("dep", flight.origin, flight.departure), ("arr", flight.destination, flight.arrival)):
            record[prefix] = {"scheduled": local_stamp(stamp, airport), "estimated": None, "actual": None,
                              "terminal": None, "gate": None, "delay_minutes": None}
        if not record["arr" if side == "arrival" else "dep"]["scheduled"]:
            incomplete = True
        if matches(record, query):
            found.append(record)
            if len(found) > MAX_LOCAL:
                return found[:MAX_LOCAL], True
    return found, incomplete


def search_status(query):
    signature = json.dumps(query, default=str, sort_keys=True) + settings.AIRLABS_API_KEY
    key = "status-search:" + hashlib.sha256(signature.encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached
    records, partial = [], False
    state, message = "ok", "Live schedules cover a rolling window of up to 10 hours; a full day may not be available."
    if not settings.AIRLABS_API_KEY:
        state, message = "unavailable", "AirLabs credentials are not configured."
    elif outside_window(query):
        state, message = "outside_coverage", "The selected date is outside the available live schedule window."
    else:
        if query["mode"] == "flight_number":
            params = {"flight_iata": query["flight_number"]}
        elif query["mode"] == "route":
            params = {"dep_iata": query["origin"]}
        else:
            params = {"arr_iata" if query["direction"] == "arrivals" else "dep_iata": query["airport"]}
        try:
            for page in range(MAX_PAGES):
                url = "https://airlabs.co/api/v9/schedules?" + urlencode({**params, "api_key": settings.AIRLABS_API_KEY, "limit": PAGE_SIZE, "offset": page * PAGE_SIZE})
                with urlopen(url, timeout=4) as response:
                    payload = json.load(response)
                if not isinstance(payload, dict) or payload.get("error") or not isinstance(payload.get("response"), list):
                    raise ValueError("Invalid provider response")
                batch = payload["response"]
                if len(batch) > PAGE_SIZE:
                    partial = True
                for raw in batch[:PAGE_SIZE]:
                    record = normalize(raw) if isinstance(raw, dict) else None
                    if record and matches(record, query):
                        records.append(record)
                    if record is None:
                        partial = True
                    elif not record["arr" if query["mode"] == "airport" and query["direction"] == "arrivals" else "dep"]["scheduled"]:
                        partial = True
                meta = payload.get("request") or {}
                more = meta.get("has_more") if isinstance(meta, dict) else None
                if more is False or (more is None and len(batch) < PAGE_SIZE):
                    break
                if page == MAX_PAGES - 1:
                    partial = True
        except (URLError, OSError, ValueError, TypeError, OverflowError):
            if records:
                partial = True
                message = "AirLabs stopped responding before all pages were received. Showing partial live results."
            else:
                state, message = "unavailable", "AirLabs is currently unavailable. Please try again shortly."
    provider_state = state
    if state != "ok":
        records, partial = local_records(query)
        if records:
            state = "fallback"
            message += " Showing matching local records; these are not live provider updates."
    elif not records:
        state = "empty"
    side = "arr" if query["mode"] == "airport" and query["direction"] == "arrivals" else "dep"
    unique = {(row["number"], row["origin"], row["destination"], row["dep"]["scheduled"], row["arr"]["scheduled"]): row for row in records}
    result = {"state": state, "provider_state": provider_state, "message": message, "partial": partial,
              "coverage_limited": provider_state == "ok", "checked_at": timezone.now().isoformat(),
              "results": sorted(unique.values(), key=lambda row: (row[side]["scheduled"] or "", row["number"]))}
    cache.set(key, result, timeout=45 if provider_state == "ok" else 15)
    return result

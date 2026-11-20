import json
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Flight


def optional_text(value):
    return (str(value).strip() or None) if isinstance(value, (str, int)) and not isinstance(value, bool) else None


def arrival_stamp(data, field, airport):
    """Return an aware instant, never interpret airport-local data as server time."""
    from .status_search import zone
    try:
        stamp = data.get(field + "_ts")
        if stamp is not None:
            return datetime.fromtimestamp(float(stamp), dt_timezone.utc).isoformat()
        utc = data.get(field + "_utc")
        value = parse_datetime(str(utc or data.get(field) or ""))
        if value is None:
            return None
        if timezone.is_naive(value):
            local_zone = ZoneInfo("UTC") if utc else zone(airport)
            if local_zone is None:
                return None
            value = value.replace(tzinfo=local_zone)
        return value.isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def provider_status(value, departure_delay=0):
    return {
        "scheduled": Flight.Status.DELAYED if departure_delay > 0 else Flight.Status.ON_TIME,
        "delayed": Flight.Status.DELAYED,
        "active": Flight.Status.DEPARTED, "en-route": Flight.Status.DEPARTED,
        "landed": Flight.Status.LANDED, "cancelled": Flight.Status.CANCELLED, "canceled": Flight.Status.CANCELLED,
    }.get(value, "unknown")


def lookup(flight):
    url = "https://airlabs.co/api/v9/flight?" + urlencode({
        "flight_iata": flight.number, "api_key": settings.AIRLABS_API_KEY,
    })
    try:
        with urlopen(url, timeout=4) as response:
            payload = json.load(response)
        data = payload.get("response", {})
        if not isinstance(data, dict):
            return None
        stamp = data.get("dep_time_ts")
        if stamp is not None:
            difference = abs(float(stamp) - flight.departure.timestamp())
        else:
            departure = parse_datetime(str(data.get("dep_time_utc", "")) + "Z")
            if departure is None:
                return None
            difference = abs((departure - flight.departure).total_seconds())
        if (difference > 60 or data.get("dep_iata") != flight.origin
                or data.get("arr_iata") != flight.destination or data.get("flight_iata") != flight.number):
            return None
        status = provider_status(data.get("status"), float(data.get("dep_delayed") or 0))
        if status != "unknown":
            return {
                "status": status, "source": "airlabs", "checked_at": timezone.now().isoformat(),
                "estimated_arrival": arrival_stamp(data, "arr_estimated", flight.destination),
                "actual_arrival": arrival_stamp(data, "arr_actual", flight.destination),
                "terminal": optional_text(data.get("arr_terminal")),
                "baggage": optional_text(data.get("arr_baggage")),
            }
    except (URLError, OSError, ValueError, TypeError, AttributeError):
        return None
    return None


def flight_status(flight):
    internal = {
        "status": flight.status, "source": "demo" if flight.demo else "airbooking",
        "checked_at": flight.status_updated_at.isoformat(),
    }
    if flight.demo or not settings.AIRLABS_API_KEY:
        return internal
    key = f"flight-status:{flight.pk}:{flight.number}:{flight.origin}:{flight.destination}:{flight.departure.timestamp()}:{flight.status_updated_at.timestamp()}"
    live = cache.get_or_set(key, lambda: lookup(flight) or {}, timeout=60)
    return live or internal

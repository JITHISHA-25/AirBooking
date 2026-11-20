# AirBooking API

Base URL `http://127.0.0.1:8000/api`. Use JSON and keep the trailing slash on the paths below. Send `Authorization: Bearer <access>` on traveler or admin requests. Admin routes also require Django staff access. The refresh and logout endpoints use the refresh token supplied in the JSON body.

## Authentication and users

| Method | Path | Access | Request / result |
| --- | --- | --- | --- |
| POST | `/auth/register/` | Public | `username`, `email`, `password`, optional `first_name` and `last_name`. Returns 201 and the pending account. |
| POST | `/auth/login/` | Public | `username` and `password`. Returns `access`, `refresh`, `user`. Pending or rejected credentials return 403. |
| POST | `/auth/token/refresh/` | Refresh token | `refresh`. Returns a new access and refresh pair and blacklists the old refresh token. |
| GET | `/auth/me/` | Signed in | Returns the current account. |
| POST | `/auth/logout/` | Refresh token | `refresh`. Blacklists the supplied refresh token and returns 204. |
| GET | `/admin/users/` | Admin | Lists accounts and their approval status. |
| GET | `/admin/users/pending/` | Admin | Lists accounts awaiting review. |
| GET | `/admin/users/{id}/` | Admin | Returns one account. |
| POST | `/admin/users/{id}/approve/` | Admin | Empty body. Approves the account and dispatches an activation email on a status change. |
| POST | `/admin/users/{id}/reject/` | Admin | Empty body. Rejects the account and blocks its protected requests and refreshes. |

## Flights and status

| Method | Path | Access | Request / result |
| --- | --- | --- | --- |
| GET | `/flights/search/` | Signed in | Optional `origin`, `destination`, `airport`, `date` in YYYY-MM-DD for IST, `seats` from 1 to 9 and `available` as true or false. |
| GET | `/flights/{id}/` | Signed in | Returns itinerary, price, seat inventory and stored status. |
| GET | `/flights/{id}/status/` | Signed in | Returns `status`, `checked_at` and `source` as `airlabs`, `airbooking` or `demo`. |
| GET | `/admin/flights/` | Admin | Lists all flight records. |
| POST | `/admin/flights/` | Admin | Creates a flight. Sets available seats to capacity. |
| GET | `/admin/flights/{id}/` | Admin | Returns one flight. |
| PUT, PATCH | `/admin/flights/{id}/` | Admin | Updates a flight. Capacity changes retain the number of seats already reserved. |
| PUT | `/admin/flights/{id}/status/` | Admin | Example body `{"status":"delayed"}`. |
| DELETE | `/admin/flights/{id}/` | Admin | Deletes a flight with no booking history and returns 204. |
| GET | `/admin/stats/` | Admin | Returns `pending_users`, `flights`, `confirmed_bookings` and `confirmed_seats`. |

Example search `GET /api/flights/search/?origin=COK&destination=BLR&adults=2&children=1&infants=0&cabin_class=business&available=true`. `airport` matches either endpoint. By default the API returns future flights with enough seats and a bookable status. Set `available=false` to include all matching future flights regardless of seat count and booking status.

Optional `cabin_class` values are `economy`, `premium_economy`, `business` and `first`. Each option filters the exact cabin class. Each flight inventory record has one cabin class and its own listed fare and seat capacity. Admin flight creation and editing accept `cabin_class`; existing flights default to Economy.

Traveller counts use `adults` (1–9, age 12+), `children` (0–6, age 2 to under 12), and `infants` (0–6, under 2), measured on the day of travel. The total must be at most 9, with no more infants than adults. Each traveller, including infants, reserves one seat at the listed fare. The existing `seats` parameter is still accepted; when supplied alongside traveller counts, it must match their total. Without age counts, `seats` is treated as the adult count.

Flight statuses are `on_time`, `delayed`, `cancelled`, `departed` and `landed`. Prices are serialized as decimal strings in INR. Use ISO 8601 timestamps with an explicit offset.

```json
{
  "number": "AI501",
  "airline": "Example Air",
  "origin": "COK",
  "destination": "BLR",
  "departure": "2030-07-01T09:30:00+05:30",
  "arrival": "2030-07-01T10:35:00+05:30",
  "price": "4299.00",
  "capacity": 80,
  "status": "on_time"
}
```

## Bookings

| Method | Path | Access | Request / result |
| --- | --- | --- | --- |
| POST | `/bookings/` | Signed in | `flight_id`, `seats`, optional UUID `request_id` and optional `payment` as `success` or `decline`. Returns 201 for a new booking or 200 for a matching replay. |
| GET | `/bookings/` | Signed in | Lists the signed-in traveler's reservations. |
| GET | `/bookings/{id}/` | Owner | Returns the reservation with nested flight details. |
| POST | `/bookings/{id}/cancel/` | Owner | Required `reason` (nonblank, up to 500 characters) for a confirmed booking. Returns the updated booking after cancelling and restoring inventory. Repeat requests return the cancelled booking and preserve its original reason. |

```json
{
  "flight_id": 1,
  "seats": 2,
  "request_id": "44e5e8bc-65cd-4ee1-b285-3d5f23a68ccf",
  "payment": "success"
}
```

Booking creation also accepts the `adults`, `children` and `infants` fields described above, deriving `seats` from their sum. Responses preserve these counts. Existing reservations are migrated as adult travellers. Cabin class is shown in the nested flight. An administrator cannot change a flight's cabin class while seats are reserved.

The server saves the unit fare at booking time and returns `reference`, `unit_price`, `total`, `status` and `payment_status`. Retry the same booking with the original `request_id`. A reused ID for a different flight, seat quantity or traveller breakdown returns 409. Booking IDs are numeric path parameters and the confirmation reference is a UUID.

Traveler-initiated cancellations are accepted before scheduled departure, or when an administrator has marked the flight cancelled. Departed or landed flights are closed for cancellation. Send a body such as `{"reason":"Change of travel plans"}`. Booking responses include `cancellation_reason`; existing cancellations without a saved reason keep an empty string. Payments and refunds are simulations. A decline returns 402 with no inventory change.

## Flight Status (read-only)

`GET /flights/status/search/` requires an approved signed-in account. Required fields: `mode` (`airport`, `route`, `flight_number`) and `date` (`YYYY-MM-DD`).

- Airport mode: required `airport`, optional `direction` (`departures` by default or `arrivals`), optional `destination` for departures or `origin` for arrivals.
- Route mode: required `origin` and `destination`.
- Flight-number mode: required `flight_number`; whitespace is removed and letters are uppercased (`6E 2009` → `6E2009`).

Example: `/flights/status/search/?mode=airport&airport=DEL&direction=departures&destination=BLR&date=2026-11-20`.

The response contains `state` (`ok`, `empty`, `fallback`, `unavailable`, `outside_coverage`), `provider_state`, `message`, `checked_at`, `partial`, `coverage_limited`, and `results`. Provider outages return an explanatory 200 response with no results or labeled local fallbacks; invalid inputs return 400. Tracking never changes inventory or bookings.

Each result has `number`, optional `airline`, `origin`, `destination`, `status`, `source` (`AirLabs`, `AirBooking`, `Demo`), optional `baggage`, and `dep`/`arr` objects. These objects contain `scheduled`, `estimated`, `actual`, `terminal`, `gate`, and `delay_minutes`. Time strings use `YYYY-MM-DD HH:mm` in that airport's local timezone; absent fields are null. Dates match scheduled local departures except for arrival boards, which match scheduled local arrivals. Unknown provider statuses map to `unknown`.

AirLabs Live Schedules has limited rolling coverage (up to ten hours ahead). Responses cache for 45 seconds, or 15 seconds when unavailable/falling back. Each page times out after four seconds; no more than three 50-record pages are requested. `partial` signals truncation, missing date information, or incomplete provider pagination. An empty response never means a flight does not operate outside that window.

## Complaints

| Method | Path | Access | Request / result |
| --- | --- | --- | --- |
| POST | `/complaints/` | Signed in | Required `subject` (up to 160 characters) and `message` (up to 5,000 characters). Returns 201 with the saved complaint. |
| GET | `/complaints/` | Signed in | Lists only the current user's complaints, newest first. |
| GET | `/complaints/{id}/` | Owner | Returns one complaint. Other users receive 404. |
| GET | `/admin/complaints/` | Admin | Lists all complaints, newest first, including the sender's `username` and `email`. |
| GET | `/admin/complaints/{id}/` | Admin | Returns one complaint and its sender details. |

Complaints include `id`, `subject`, `message` and `created_at`. The server assigns the sender from the authenticated account. Blank or whitespace-only subjects and messages are rejected. Submitted complaints cannot be edited or deleted through these endpoints.

## Error responses

Field validation returns 400 with messages keyed by field name. Other errors generally use a `detail` string. Common codes include 401 for missing or expired access, 403 for insufficient permissions, 404 for missing records or reservations owned by another traveler, 409 for inventory or state conflicts, and 429 for throttled login or registration attempts.

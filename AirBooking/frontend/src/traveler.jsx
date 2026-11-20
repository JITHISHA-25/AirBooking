import { useState, useSyncExternalStore } from 'react'
import { ArrowLeft, ArrowRight, BriefcaseBusiness, CircleCheck, Eye, EyeOff, Plane, Radio, Search, Utensils } from 'lucide-react'
import { Link, Navigate, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, getSession, register, signIn, subscribe } from './api'
import { cabinLabel, TravelOptions, travellerCount, travellerSummary } from './travel-options'
import { TripFood } from './food'
import {
  AirportField, AirportOptions, canBook, dateTime, Empty, FlightCard,
  LiveStatus, Logo, money, Notice, RouteInfo, Status, useResource,
} from './ui'

export function AuthPage({ registration = false }) {
  const navigate = useNavigate()
  const session = useSyncExternalStore(subscribe, getSession)
  const location = useLocation()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  if (session) return <Navigate to="/" replace />

  async function submit(event) {
    event.preventDefault()
    setError('')
    setBusy(true)
    const form = Object.fromEntries(new FormData(event.currentTarget))
    try {
      if (registration) {
        await register(form)
        navigate('/login', { replace: true, state: { registered: true } })
      } else {
        const user = await signIn(form)
        navigate(user.is_staff ? '/admin' : '/flights', { replace: true })
      }
    } catch (failure) {
      setError(failure.message)
    } finally {
      setBusy(false)
    }
  }

  return <main className="auth-page">
    <section className="auth-intro">
      <Logo />
      <div className="auth-intro-copy"><span className="eyebrow">A smoother journey starts here</span><h1>Less planning.<br />More possibilities.</h1>
        <p>From your first search to your next arrival, keep your journey together with AirBooking.</p>
        <ul className="auth-benefits">
          <li><Plane size={19} aria-hidden="true" /> Find flights that fit your plans</li>
          <li><Utensils size={19} aria-hidden="true" /> Add a meal to your journey</li>
          <li><Radio size={19} aria-hidden="true" /> Keep up with flight updates</li>
        </ul>
      </div>
      <small className="auth-caption">Your next chapter is a flight away.</small>
    </section>
    <section className="auth-panel">
      <div className="auth-form">
        <span className="eyebrow">{registration ? 'Start your journey' : 'Welcome back'}</span>
        <h2>{registration ? 'Create your account' : 'Sign in to AirBooking'}</h2>
        {!registration && <p>Manage your bookings, meals, and flight updates.</p>}
        {registration && <p>An administrator reviews your account before you can sign in.</p>}
        {!registration && location.state?.registered && <Notice>Registration submitted. You can sign in after an administrator approves your account.</Notice>}
        {error && <Notice error>{error}</Notice>}
        <form className="stack" onSubmit={submit}>
          {registration && <div className="field-pair">
            <label>First name<input name="first_name" autoComplete="given-name" maxLength={150} /></label>
            <label>Last name<input name="last_name" autoComplete="family-name" maxLength={150} /></label>
          </div>}
          <label>Username<input name="username" autoComplete="username" maxLength={150} required /></label>
          {registration && <label>Email<input name="email" type="email" autoComplete="email" maxLength={254} required /></label>}
          <div className="password-field"><label htmlFor="auth-password">Password</label>
            <div className="password-input"><input id="auth-password" name="password" type={showPassword ? 'text' : 'password'} autoComplete={registration ? 'new-password' : 'current-password'}
              aria-describedby={registration ? 'password-help' : undefined} minLength={registration ? 8 : undefined} maxLength={128} required />
              <button type="button" className="password-toggle" aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword}
                onClick={() => setShowPassword(show => !show)}>{showPassword ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}</button>
            </div>
            {registration && <small id="password-help">Use at least 8 characters and a password you haven’t used elsewhere.</small>}
          </div>
          <button className="button" disabled={busy}>{busy ? 'Please wait…' : registration ? 'Request an account' : 'Sign in'}
            <ArrowRight size={18} aria-hidden="true" /></button>
        </form>
        <p className="auth-switch">{registration ? 'Already have an account?' : 'New to AirBooking?'}{' '}
          <Link to={registration ? '/login' : '/register'}>{registration ? 'Sign in' : 'Create an account'}</Link>
        </p>
      </div>
    </section>
  </main>
}

const defaultSearch = { origin: '', destination: '', date: '', adults: 1, children: 0, infants: 0, cabin_class: 'economy', available: true }
const byDeparture = (a, b) => Date.parse(a.departure) - Date.parse(b.departure)
const byDuration = (a, b) => (Date.parse(a.arrival) - Date.parse(a.departure)) - (Date.parse(b.arrival) - Date.parse(b.departure))
const flightSorts = {
  departure_asc: { label: 'Departure: earliest first', compare: byDeparture },
  departure_desc: { label: 'Departure: latest first', compare: (a, b) => byDeparture(b, a) },
  price_asc: { label: 'Price: low to high', compare: (a, b) => Number(a.price) - Number(b.price) },
  price_desc: { label: 'Price: high to low', compare: (a, b) => Number(b.price) - Number(a.price) },
  duration_asc: { label: 'Duration: shortest first', compare: byDuration },
  duration_desc: { label: 'Duration: longest first', compare: (a, b) => byDuration(b, a) },
}

export function SearchPage() {
  const [form, setForm] = useState(defaultSearch)
  const [search, setSearch] = useState('')
  const [version, setVersion] = useState(0)
  const [sort, setSort] = useState('departure_asc')
  const result = useResource('/flights/search/' + (search ? '?' + search : ''), version)
  const sortedFlights = [...(result.data || [])].sort((a, b) =>
    flightSorts[sort].compare(a, b) || byDeparture(a, b) || a.id - b.id)

  function set(field, value) {
    setForm(previous => ({ ...previous, [field]: value }))
  }

  function submit(event) {
    event.preventDefault()
    const query = new URLSearchParams()
    Object.entries(form).forEach(([field, value]) => {
      if (value !== '') query.set(field, String(value))
    })
    setSearch(query.toString())
    setVersion(previous => previous + 1)
  }

  return <>
    <section className="search-hero">
      <div className="hero-content"><span className="eyebrow">Make room for your next adventure</span><h1>Find your next flight.</h1><p>Your route. Your schedule. A journey that fits.</p></div>
      <form className="search-form" onSubmit={submit}>
        <AirportOptions />
        <div className="search-fields">
          <AirportField name="origin" label="From" value={form.origin} onChange={value => set('origin', value)} />
          <AirportField name="destination" label="To" value={form.destination} onChange={value => set('destination', value)} />
          <label>Departure date<input type="date" value={form.date} onChange={event => set('date', event.target.value)} /></label>
          <TravelOptions value={form} onChange={setForm} />
          <button className="button search-submit"><Search size={17} aria-hidden="true" /> Search flights</button>
        </div>
        <label className="checkbox"><input type="checkbox" checked={form.available}
          onChange={event => set('available', event.target.checked)} /> Only show bookable flights</label>
      </form>
    </section>
    <section className="results">
      <div className="section-heading flight-results-heading">
        <div className="flight-results-title"><h2>{search ? 'Search results' : 'Upcoming flights'}</h2>
          {result.data && <span>{result.data.length} {result.data.length === 1 ? 'flight' : 'flights'}</span>}</div>
        <label className="flight-sort">Sort by<select value={sort} onChange={event => setSort(event.target.value)}>
          {Object.entries(flightSorts).map(([value, option]) => <option key={value} value={value}>{option.label}</option>)}
        </select></label>
      </div>
      {result.loading && <Notice>Loading flights…</Notice>}
      {result.error && <Notice error>{result.error}</Notice>}
      {result.data?.length === 0 && <Empty title="No matching flights">Try a different route, date, traveller count or cabin class.</Empty>}
      <div className="cards">{sortedFlights.map(flight => <FlightCard key={flight.id} flight={flight} search={search} />)}</div>
    </section>
  </>
}

export function FlightPage() {
  const { id } = useParams()
  return <FlightDetail key={id} id={id} />
}

function FlightDetail({ id }) {
  const navigate = useNavigate()
  const location = useLocation()
  const result = useResource('/flights/' + encodeURIComponent(id) + '/')
  const [travellers, setTravellers] = useState(() => {
    const query = new URLSearchParams(location.search)
    const adults = Number(query.get('adults') || 1)
    const children = Number(query.get('children') || 0)
    const infants = Number(query.get('infants') || 0)
    const valid = Number.isInteger(adults) && adults >= 1 && Number.isInteger(children) && children >= 0 && children <= 6
      && Number.isInteger(infants) && infants >= 0 && infants <= 6 && infants <= adults && adults + children + infants <= 9
    return valid ? { adults, children, infants } : { adults: 1, children: 0, infants: 0 }
  })
  const seats = travellerCount(travellers)
  const flight = result.data

  function continueToPayment(event) {
    event.preventDefault()
    if (!canBook(flight) || seats > flight.seats_available) return
    const query = new URLSearchParams({ ...travellers, request_id: crypto.randomUUID() })
    navigate('/flights/' + flight.id + '/payment?' + query)
  }

  return <>
    <Link to="/flights" className="back"><ArrowLeft size={17} aria-hidden="true" /> Back to flights</Link>
    {result.loading && <Notice>Loading flight…</Notice>}
    {result.error && <Notice error>{result.error}</Notice>}
    {flight && <>
      <div className="page-title"><h1>{flight.origin} to {flight.destination}</h1>
        <p>{flight.airline} · {flight.number}</p></div>
      <div className="detail-grid">
        <section className="panel stack"><h2>Flight details</h2><RouteInfo flight={flight} />
          <p>Departs {dateTime(flight.departure)} IST<br />Arrives {dateTime(flight.arrival)} IST</p>
          <p>Cabin class: <strong>{cabinLabel(flight.cabin_class)}</strong></p>
          <LiveStatus flight={flight} />
        </section>
        <section className="panel stack"><h2>Book your trip</h2>
          {canBook(flight) ? <form className="stack" onSubmit={continueToPayment}>
            <div className="section-heading"><span>Price per traveller</span><strong>{money(flight.price)}</strong></div>
            <TravelOptions value={travellers} cabinSelection={false} onChange={setTravellers} />
            <small>{travellerSummary(travellers)} · {flight.seats_available} seats available</small>
            <small>Each traveller, including infants, reserves one seat at the listed fare.</small>
            {seats > flight.seats_available && <Notice error>There are not enough seats for these travellers. Choose fewer travellers or another flight.</Notice>}
            <div className="section-heading total"><span>Total</span><strong>{money(Number(flight.price) * seats)}</strong></div>
            <small>Your booking is confirmed after the payment simulation succeeds.</small>
            <button className="button" disabled={seats > flight.seats_available}>Continue to payment <ArrowRight size={17} aria-hidden="true" /></button>
          </form> : <Notice>This flight is closed for bookings.</Notice>}
        </section>
      </div>
    </>}
  </>
}

const cancellationReasons = [
  'Change of travel plans',
  'Personal or family emergency',
  'Health or medical reasons',
  'Flight delayed or cancelled',
  'Booked the wrong flight or date',
  'Found a better fare',
  'Duplicate booking',
  'Visa or travel document issues',
]

export function TripsPage() {
  const location = useLocation()
  const [version, setVersion] = useState(0)
  const result = useResource('/bookings/', version)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(null)
  const [cancelId, setCancelId] = useState(null)
  const [cancelReason, setCancelReason] = useState('')
  const [foodFeedback, setFoodFeedback] = useState('')
  const reference = location.state?.reference

  async function cancel(event, id) {
    event.preventDefault()
    if (busy !== null || !cancelReason.trim()) return
    setBusy(id)
    setError('')
    try {
      await api('/bookings/' + id + '/cancel/', { method: 'POST', body: { reason: cancelReason.trim() } })
      setCancelId(null)
      setCancelReason('')
      setVersion(previous => previous + 1)
    } catch (failure) {
      setError(failure.message)
    } finally {
      setBusy(null)
    }
  }

  return <>
    <div className="page-title"><span className="eyebrow">Your travel plans</span><h1>My Trips</h1><p>Bookings, meals, and flight updates — together in one place.</p></div>
    {reference && result.data?.some(booking => booking.reference === reference && booking.status === 'confirmed') &&
      <Notice><CircleCheck size={18} aria-hidden="true" /> Booking confirmed. Reference {reference}</Notice>}
    {result.error && <Notice error>{result.error}</Notice>}
    {error && <Notice error>{error}</Notice>}
    {foodFeedback && <Notice>{foodFeedback}</Notice>}
    {result.loading && <Notice>Loading trips…</Notice>}
    {result.data?.length === 0 && <Empty title="No trips yet"><Link to="/flights">Find a flight</Link> to make your first booking.</Empty>}
    <div className="cards">
      {result.data?.map(booking => {
        const flight = booking.flight
        const confirmed = booking.status === 'confirmed'
        const cancellable = confirmed && !['departed', 'landed'].includes(flight.status) &&
          (Date.parse(flight.departure) > Date.now() || flight.status === 'cancelled')
        return <article className="panel trip-card" key={booking.id}>
          <div className="section-heading"><div className="flight-identity"><span className="icon-tile">
            <BriefcaseBusiness size={20} aria-hidden="true" /></span><div><h2>{flight.origin} to {flight.destination}</h2>
            <small>{flight.airline} · {flight.number}</small></div></div><Status value={booking.status} /></div>
          <RouteInfo flight={flight} />
          <LiveStatus flight={flight} enabled={confirmed && Date.parse(flight.arrival) > Date.now() - 3600000} />
          <div className="trip-meta">
            <span>Booking reference<strong className="reference">{booking.reference}</strong></span>
            <span>Departure<strong>{dateTime(flight.departure)} IST</strong></span>
            <span>{booking.seats} {booking.seats === 1 ? 'traveller' : 'travellers'}<strong>{money(booking.total)}</strong>
              <small>{travellerSummary(booking)}</small><small>{cabinLabel(flight.cabin_class)}</small></span>
            <span>Payment<strong>{booking.payment_status === 'paid' ? 'Paid' : 'Refunded'} (simulated)</strong></span>
          </div>
          {!confirmed && booking.cancellation_reason && <p className="cancellation-reason"><strong>Cancellation reason:</strong> {booking.cancellation_reason}</p>}
          <TripFood booking={booking} onChanged={message => { setFoodFeedback(message); setVersion(value => value + 1) }} />
          {cancellable && (cancelId === booking.id ?
            <form className="stack cancellation-form" onSubmit={event => cancel(event, booking.id)}>
              <h3>Why are you cancelling this trip?</h3>
              <label>Common reasons<select disabled={busy !== null}
                value={cancellationReasons.includes(cancelReason) ? cancelReason : ''}
                onChange={event => setCancelReason(event.target.value)}>
                <option value="">Other / write your own reason</option>
                {cancellationReasons.map(reason => <option key={reason} value={reason}>{reason}</option>)}
              </select></label>
              <label>Cancellation reason<textarea name="reason" rows={3} maxLength={500} required disabled={busy !== null}
                value={cancelReason} onChange={event => setCancelReason(event.target.value)}
                placeholder="Choose a common reason above or type your own reason." />
                <small>You can edit a selected reason. Up to 500 characters.</small>
              </label>
              <p>Confirm to cancel this trip and issue a simulated refund. Any active food order will also be cancelled and refunded in the same transaction.</p>
              <div className="action-row">
                <button className="button button-danger" disabled={busy !== null || !cancelReason.trim()}>
                  {busy === booking.id ? 'Cancelling…' : 'Confirm cancellation'}</button>
                <button type="button" className="button button-secondary" disabled={busy !== null}
                  onClick={() => { setCancelId(null); setCancelReason(''); setError('') }}>Keep trip</button>
              </div>
            </form> : <button className="button button-secondary" disabled={busy !== null}
              onClick={() => { setCancelId(booking.id); setCancelReason(''); setError('') }}>Cancel trip</button>)}
        </article>
      })}
    </div>
  </>
}

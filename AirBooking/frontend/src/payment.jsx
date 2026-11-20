import { useRef, useState } from 'react'
import { ArrowLeft, ShieldCheck } from 'lucide-react'
import { Link, Navigate, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from './api'
import { canBook, dateTime, money, Notice, RouteInfo, useResource } from './ui'
import { cabinLabel, travellerCount, travellerSummary } from './travel-options'
import { FoodSelector, foodItems, foodSubtotal, useFoodCutoff } from './food'
import { SimulationControls } from './payment-simulation'

export function PaymentPage() {
  const { id } = useParams()
  const location = useLocation()
  const query = new URLSearchParams(location.search)
  const travellers = {
    adults: Number(query.get('adults')),
    children: Number(query.get('children')),
    infants: Number(query.get('infants')),
  }
  const seats = travellerCount(travellers)
  const requestId = query.get('request_id') || ''
  const valid = Number.isInteger(travellers.adults) && travellers.adults >= 1
    && Number.isInteger(travellers.children) && travellers.children >= 0 && travellers.children <= 6
    && Number.isInteger(travellers.infants) && travellers.infants >= 0 && travellers.infants <= 6
    && travellers.infants <= travellers.adults && seats <= 9
    && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(requestId)
  if (!valid) return <Navigate to={'/flights/' + encodeURIComponent(id)} replace />
  return <PaymentCheckout key={id + location.search} id={id} travellers={travellers} requestId={requestId} />
}

function PaymentCheckout({ id, travellers, requestId }) {
  const navigate = useNavigate()
  const result = useResource('/flights/' + encodeURIComponent(id) + '/')
  const menu = useResource('/flights/' + encodeURIComponent(id) + '/meals/')
  const [selected, setSelected] = useState({})
  const [method, setMethod] = useState('card')
  const [outcome, setOutcome] = useState('success')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState(null)
  const submitting = useRef(false)
  const flight = result.data
  const seats = travellerCount(travellers)
  const editLink = '/flights/' + encodeURIComponent(id) + '?' + new URLSearchParams(travellers)
  const fare = flight ? Number(flight.price) * seats : 0
  const foodTotal = foodSubtotal(menu.data?.meals, selected)
  const total = (Math.round(fare * 100) + Math.round(foodTotal * 100)) / 100
  const cutoffPassed = useFoodCutoff(menu.data?.cutoff)
  const foodReady = !foodItems(selected).length || (menu.data?.available && !cutoffPassed)
  const available = flight && canBook(flight) && seats <= flight.seats_available

  async function pay(event) {
    event.preventDefault()
    if (submitting.current || !available || !foodReady) return
    submitting.current = true
    setBusy(true)
    setFailure(null)
    try {
      const booking = await api('/bookings/', {
        method: 'POST',
        body: { flight_id: flight.id, ...travellers, seats, meals: foodItems(selected), payment: outcome, request_id: requestId },
      })
      navigate('/trips', { replace: true, state: { reference: booking.reference } })
    } catch (error) {
      setFailure({ message: error.message, declined: error.status === 402 })
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  return <>
    <Link to={editLink} className="back" onClick={event => { if (busy) event.preventDefault() }}>
      <ArrowLeft size={17} aria-hidden="true" /> Back to flight</Link>
    <div className="page-title"><h1>Payment simulation</h1><p>Review your trip and complete a test payment to book your tickets.</p></div>
    <Notice><ShieldCheck size={19} aria-hidden="true" /> Payments are simulated. No real money is charged and no payment details are collected.</Notice>
    {result.loading && <Notice>Loading your trip...</Notice>}
    {result.error && <Notice error>{result.error}</Notice>}
    {flight && <div className="detail-grid payment-grid">
      <section className="panel stack" aria-labelledby="payment-summary-title">
        <h2 id="payment-summary-title">Your trip</h2>
        <p><strong>{flight.airline} · {flight.number}</strong></p>
        <RouteInfo flight={flight} />
        <p>Departs {dateTime(flight.departure)} IST<br />Arrives {dateTime(flight.arrival)} IST</p>
        <div className="payment-summary">
          <div><span>Cabin class</span><strong>{cabinLabel(flight.cabin_class)}</strong></div>
          <div><span>Travellers</span><strong>{travellerSummary(travellers)}</strong></div>
          <div><span>{seats} × {money(flight.price)}</span><strong>{money(fare)}</strong></div>
        </div>
        <small>Each traveller, including infants, reserves one seat at the listed fare. Seats are reserved when payment succeeds.</small>
        <FoodSelector menu={menu} selected={selected} onChange={setSelected} seats={seats} disabled={busy} />
        <div className="payment-summary"><div><span>Flight fare</span><strong>{money(fare)}</strong></div>
          <div><span>Food subtotal</span><strong>{money(foodTotal)}</strong></div></div>
        <div className="section-heading total"><span>Combined total (simulated)</span><strong>{money(total)}</strong></div>
      </section>
      <section className="panel stack" aria-labelledby="payment-method-title">
        <h2 id="payment-method-title">Choose a test payment</h2>
        {!available && <Notice error>This flight no longer has enough bookable seats for your party. Return to the flight to review availability.</Notice>}
        <form className="stack" onSubmit={pay} aria-busy={busy}>
          <SimulationControls method={method} setMethod={setMethod} outcome={outcome} setOutcome={setOutcome} disabled={busy} />
          {failure && <div className="payment-feedback"><Notice error>{failure.declined ? 'Payment declined. No ticket was booked and no seats were reserved. Select Successful payment to try again.' : failure.message}</Notice></div>}
          <button className="button" disabled={busy || !available || !foodReady}>
            {busy ? 'Processing test payment...' : `Pay ${money(total)} (simulated)`}
          </button>
          <small>{busy ? 'Please wait while your booking is confirmed.' : 'Successful payments confirm your booking. Declined payments leave it unbooked.'}</small>
        </form>
      </section>
    </div>}
  </>
}

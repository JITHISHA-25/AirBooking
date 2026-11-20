import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { dateTime, money, Notice, useResource } from './ui'
import { SimulationControls } from './payment-simulation'
import { mealLabel } from './display-labels'

export const foodItems = selected => Object.entries(selected).filter(([, quantity]) => quantity > 0)
  .map(([id, quantity]) => ({ meal_id: Number(id), quantity })).sort((a, b) => a.meal_id - b.meal_id)

export const foodSubtotal = (meals = [], selected) => meals.reduce((cents, meal) =>
  cents + Math.round(Number(meal.price) * 100) * (selected[meal.id] || 0), 0) / 100

export function useFoodCutoff(cutoff) {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    setNow(Date.now())
    if (!cutoff) return
    const timer = setTimeout(() => setNow(Date.now()), Math.max(0, Date.parse(cutoff) - Date.now()))
    return () => clearTimeout(timer)
  }, [cutoff])
  return !!cutoff && now >= Date.parse(cutoff)
}

export function FoodSelector({ menu, selected, onChange, seats, disabled = false }) {
  const passed = useFoodCutoff(menu.data?.cutoff)
  const count = foodItems(selected).reduce((sum, item) => sum + item.quantity, 0)
  const available = menu.data?.available && !passed
  return <section className="stack food-selector" aria-label="Pre-order food">
    <h3>Pre-order food <small>(optional)</small></h3>
    <p>Payments and refunds are simulated; this does not arrange meal delivery or airline fulfillment.</p>
    {menu.loading && <Notice>Loading the flight menu…</Notice>}
    {menu.error && <Notice error>{menu.error} You can still book without food.</Notice>}
    {menu.data && <>
      <small>Ordering and food cancellation close {dateTime(menu.data.cutoff)} (Asia/Kolkata).</small>
      {!available ? <Notice>{passed ? 'The food ordering cutoff has passed.' : menu.data.reason}</Notice>
        : menu.data.meals.length === 0 ? <Notice>No meals are available for this flight. Food is optional.</Notice>
          : <>
            <div className="meal-selection-summary"><p aria-live="polite"><strong>{count} of {seats} meals selected</strong><small>Choose up to one meal per reserved seat.</small></p>
              <progress value={count} max={seats} aria-label="Meals selected" />
            </div>
            <div className="meal-grid">{menu.data.meals.map(meal => <article className={'meal-card' + (selected[meal.id] > 0 ? ' meal-selected' : '')} key={meal.id}>
              <div><h4>{mealLabel(meal.name)}</h4><span className="meal-category">{meal.category === 'vegetarian' ? 'Vegetarian' : 'Non-vegetarian'}</span></div>
              <p>{mealLabel(meal.description) || 'No description supplied.'}</p>
              <p className="meal-notes"><strong>Ingredients / allergens:</strong> {meal.ingredient_notes || 'Not provided by admin. Do not assume allergen-free.'}</p>
              <strong>{money(meal.price)}</strong>
              <label>Quantity<select aria-label={'Quantity for ' + mealLabel(meal.name)} disabled={disabled} value={selected[meal.id] || 0}
                onChange={event => onChange({ ...selected, [meal.id]: Number(event.target.value) })}>
                {Array.from({ length: seats - count + (selected[meal.id] || 0) + 1 }, (_, quantity) =>
                  <option key={quantity} value={quantity}>{quantity}</option>)}
              </select></label>
            </article>)}</div>
          </>}
    </>}
    {count > 0 && <button type="button" className="button button-secondary" disabled={disabled} onClick={() => onChange({})}>Remove selected meals</button>}
  </section>
}

export function FoodOrderDetails({ order }) {
  return <article className="food-order stack">
    <div className="section-heading"><strong>Food order #{order.id}</strong>
      <span>{order.status === 'active' ? 'Active' : 'Cancelled'} · {order.payment_status === 'paid' ? 'Paid' : 'Refunded'} (simulated)</span></div>
    <ul>{order.items.map(item => <li key={item.meal_id}>{mealLabel(item.purchased_name)} × {item.quantity} · {money(item.unit_price)} each · {money(item.line_total)}</li>)}</ul>
    <p><strong>Food total: {money(order.total)}</strong></p>
    {order.cancellation_reason && <p>{order.cancellation_reason}. Simulated refund recorded {dateTime(order.refunded_at)} (Asia/Kolkata).</p>}
  </article>
}

export function TripFood({ booking, onChanged }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState(null)
  const pending = useRef(false)
  const passed = useFoodCutoff(booking.food_cutoff)
  const active = booking.food_orders?.find(order => order.status === 'active')
  async function cancel(order) {
    if (pending.current) return
    pending.current = true; setBusy(true); setFeedback(null)
    try {
      await api(`/bookings/${booking.id}/food-orders/${order.id}/cancel/`, { method: 'POST' })
      onChanged('Food order cancelled. A simulated food refund was recorded.')
    } catch (failure) { setFeedback({ error: true, message: failure.message }) }
    finally { pending.current = false; setBusy(false) }
  }
  return <section className="trip-food stack" aria-label="Food pre-orders">
    <h3>Food pre-orders</h3>
    <small>Payments are simulated; no real charges or airline fulfillment. Cutoff: {dateTime(booking.food_cutoff)} (Asia/Kolkata).</small>
    {booking.food_orders?.map(order => <FoodOrderDetails key={order.id} order={order} />)}
    {active && <button type="button" className="button button-secondary" disabled={busy || passed} onClick={() => cancel(active)}>
      {busy ? 'Cancelling food…' : 'Cancel food order & simulate refund'}</button>}
    {feedback && <Notice error={feedback.error}>{feedback.message}</Notice>}
    <div className="payment-summary"><div><span>Flight fare</span><strong>{money(booking.total)}</strong></div>
      <div><span>Active food total</span><strong>{money(booking.food_total || 0)}</strong></div>
      <div><span>Combined reservation total</span><strong>{money(booking.combined_total || booking.total)}</strong></div></div>
    {booking.food_available && !passed ? <>
      <button type="button" className="button button-secondary" disabled={busy} aria-expanded={open} onClick={() => setOpen(value => !value)}>
        {open ? 'Close food selection' : 'Pre-order food'}</button>
      {open && <TripFoodCheckout booking={booking} onChanged={onChanged} />}
    </> : <small>{passed ? 'Food ordering and voluntary food cancellation are now closed.' : booking.food_unavailable_reason}</small>}
  </section>
}

function TripFoodCheckout({ booking, onChanged }) {
  const menu = useResource(`/flights/${booking.flight.id}/meals/`)
  const [selected, setSelected] = useState({})
  const [method, setMethod] = useState('card')
  const [outcome, setOutcome] = useState('success')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState('')
  const pending = useRef(false)
  const request = useRef(null)
  const passed = useFoodCutoff(menu.data?.cutoff)
  const subtotal = foodSubtotal(menu.data?.meals, selected)
  const items = foodItems(selected)
  const available = items.length > 0 && menu.data?.available && !passed
  async function pay(event) {
    event.preventDefault()
    if (pending.current || !available) return
    const signature = JSON.stringify({ items, payment: outcome })
    if (request.current?.signature !== signature) request.current = { signature, id: crypto.randomUUID() }
    pending.current = true; setBusy(true); setFailure('')
    try {
      await api(`/bookings/${booking.id}/food-orders/`, { method: 'POST', body: { items, payment: outcome, request_id: request.current.id } })
      onChanged('Food pre-order confirmed. Payment is simulated; no airline fulfillment is arranged.')
    } catch (error) { setFailure(error.message) }
    finally { pending.current = false; setBusy(false) }
  }
  return <form className="stack" onSubmit={pay} aria-busy={busy}>
    <FoodSelector menu={menu} selected={selected} onChange={setSelected} seats={booking.seats} disabled={busy} />
    <div className="payment-summary"><div><span>Already booked flight fare</span><strong>{money(booking.total)}</strong></div>
      <div><span>Food subtotal / additional simulated payment</span><strong>{money(subtotal)}</strong></div>
      <div><span>Combined total after purchase</span><strong>{money((Math.round(Number(booking.total) * 100) + Math.round(subtotal * 100)) / 100)}</strong></div></div>
    <SimulationControls method={method} setMethod={setMethod} outcome={outcome} setOutcome={setOutcome} disabled={busy} prefix={'food-' + booking.id} />
    {failure && <Notice error>{failure}</Notice>}
    <button className="button" disabled={busy || !available}>{busy ? 'Processing food payment…' : `Pay ${money(subtotal)} for food (simulated)`}</button>
  </form>
}

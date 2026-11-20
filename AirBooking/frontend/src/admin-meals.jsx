import { useRef, useState } from 'react'
import { api } from './api'
import { dateTime, Empty, money, Notice, useResource } from './ui'
import { FoodOrderDetails } from './food'
import { mealLabel } from './display-labels'

function MealEditor({ meal, onClose, onSaved }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef(false)
  async function submit(event) {
    event.preventDefault()
    if (pending.current) return
    const form = new FormData(event.currentTarget)
    const body = Object.fromEntries(form)
    body.active = form.has('active')
    pending.current = true; setBusy(true); setError('')
    try {
      await api('/admin/meals/' + (meal ? meal.id + '/' : ''), { method: meal ? 'PATCH' : 'POST', body })
      onSaved(meal ? 'Meal updated. Existing purchases retain their original name and price.' : 'Meal created. Assign it to a flight to make it available.')
    } catch (failure) { setError(failure.message) }
    finally { pending.current = false; setBusy(false) }
  }
  return <section className="panel editor stack"><h3>{meal ? 'Edit meal' : 'Create meal'}</h3>
    <form className="stack" onSubmit={submit}>
      <fieldset className="food-editor-fields stack" disabled={busy}>
        <label>Meal name<input name="name" required maxLength={120} defaultValue={mealLabel(meal?.name)} /></label>
        <label>Description<textarea name="description" rows={2} maxLength={2000} defaultValue={mealLabel(meal?.description)} /></label>
        <div className="field-pair"><label>Category<select name="category" defaultValue={meal?.category || 'vegetarian'}>
          <option value="vegetarian">Vegetarian</option><option value="non_vegetarian">Non-vegetarian</option></select></label>
          <label>Price (INR)<input type="number" name="price" min="0.01" max="99999999.99" step="0.01" required defaultValue={meal?.price} /></label></div>
        <label>Ingredients / allergen notes<textarea name="ingredient_notes" rows={3} maxLength={2000} defaultValue={meal?.ingredient_notes} /></label>
        <label className="meal-toggle"><input type="checkbox" name="active" defaultChecked={meal?.active ?? true} /> Active for future purchases</label>
      </fieldset>
      {error && <Notice error>{error}</Notice>}
      <div className="action-row"><button className="button" disabled={busy}>{busy ? 'Saving…' : 'Save meal'}</button>
        <button type="button" className="button button-secondary" disabled={busy} onClick={onClose}>Close editor</button></div>
    </form>
  </section>
}

export function AdminMealsPanel({ catalog, onChanged }) {
  const flights = useResource('/admin/flights/')
  const [flightId, setFlightId] = useState('')
  const [editor, setEditor] = useState(null)
  const chosen = flightId || String(flights.data?.[0]?.id || '')
  return <div className="stack">
    <Notice>Payments and refunds are simulated. Orders do not arrange airline catering or charge real money.</Notice>
    <div className="section-heading"><h2>Meal catalog</h2><button type="button" className="button" onClick={() => setEditor({ create: true })}>Create meal</button></div>
    {editor && <MealEditor key={'meal-editor-' + (editor.id || 'new')} meal={editor.create ? null : editor} onClose={() => setEditor(null)}
      onSaved={message => { setEditor(null); onChanged(message) }} />}
    {catalog.loading && <Notice>Loading meals…</Notice>}
    {catalog.error && <Notice error>{catalog.error}</Notice>}
    {catalog.data?.length === 0 && <Empty title="No meals yet">Create a catalog meal, then assign it to a flight.</Empty>}
    <div className="meal-grid">{catalog.data?.map(meal => <article className="panel stack" key={meal.id}>
      <h3>{mealLabel(meal.name)}</h3><p>{mealLabel(meal.description)}</p>
      <p>{meal.category === 'vegetarian' ? 'Vegetarian' : 'Non-vegetarian'} · {money(meal.price)} · {meal.active ? 'Active' : 'Inactive'}</p>
      <p>Ingredients / allergens: {meal.ingredient_notes || 'Not supplied'}</p>
      <button type="button" className="button button-secondary" onClick={() => setEditor(meal)}>Edit / deactivate {mealLabel(meal.name)}</button>
    </article>)}</div>
    <h2>Flight menu & food orders</h2>
    {flights.loading && <Notice>Loading flights…</Notice>}
    {flights.error && <Notice error>{flights.error}</Notice>}
    {flights.data?.length === 0 && <Notice>Create a flight before assigning meals.</Notice>}
    {flights.data?.length > 0 && <label>Flight for meals and orders<select value={chosen} onChange={event => setFlightId(event.target.value)}>
      {flights.data.map(flight => <option key={flight.id} value={flight.id}>{flight.number} · {flight.origin} → {flight.destination} · {dateTime(flight.departure)} IST</option>)}
    </select></label>}
    {chosen && catalog.data && <FlightMeals key={'flight-menu-' + chosen} flightId={chosen} catalog={catalog.data}
      flight={flights.data?.find(flight => String(flight.id) === chosen)} />}
  </div>
}

function FlightMeals({ flightId, catalog, flight }) {
  const [version, setVersion] = useState(0)
  const assignment = useResource(`/admin/flights/${flightId}/meals/`, version)
  const report = useResource(`/admin/flights/${flightId}/food-orders/`, version)
  const [feedback, setFeedback] = useState(null)
  const [busy, setBusy] = useState(false)
  const pending = useRef(false)
  async function save(event) {
    event.preventDefault()
    if (pending.current) return
    const form = new FormData(event.currentTarget)
    pending.current = true; setBusy(true); setFeedback(null)
    try {
      await api(`/admin/flights/${flightId}/meals/`, { method: 'PUT', body: {
        meal_ids: form.getAll('meal_ids').map(Number), food_ordering_open: form.has('food_ordering_open'),
      } })
      setFeedback({ message: 'Flight menu saved. Historical food orders are unchanged.' })
      setVersion(value => value + 1)
    } catch (failure) { setFeedback({ error: true, message: failure.message }) }
    finally { pending.current = false; setBusy(false) }
  }
  return <section className="panel stack">
    {assignment.loading && <Notice>Loading flight menu…</Notice>}
    {assignment.error && <Notice error>{assignment.error}</Notice>}
    {assignment.data && <form className="stack" onSubmit={save} key={version}>
      <fieldset className="food-editor-fields stack" disabled={busy}>
        <legend>Meals assigned to this flight</legend>
        <label className="meal-toggle"><input type="checkbox" name="food_ordering_open" disabled={flight?.status === 'cancelled'}
          defaultChecked={assignment.data.food_ordering_open} /> Open food ordering (cutoff and flight-status rules still apply)</label>
        {catalog.map(meal => <label className="meal-toggle" key={meal.id}>
          <input type="checkbox" name="meal_ids" value={meal.id} defaultChecked={assignment.data.meal_ids.includes(meal.id)} />
          {mealLabel(meal.name)} · {money(meal.price)}{!meal.active ? ' · Inactive: hidden from travelers' : ''}</label>)}
      </fieldset>
      <button className="button" disabled={busy}>{busy ? 'Saving menu…' : 'Save flight menu'}</button>
    </form>}
    {feedback && <Notice error={feedback.error}>{feedback.message}</Notice>}
    <div className="section-heading"><h3>Meal quantities required</h3><button type="button" className="button button-secondary" disabled={busy || report.loading}
      onClick={() => setVersion(value => value + 1)}>Refresh food orders</button></div>
    <small>Active orders only; cancelled orders/bookings/flights are excluded.</small>
    {report.loading && <Notice>Loading food orders…</Notice>}
    {report.error && <Notice error>{report.error}</Notice>}
    {report.data?.requirements.length === 0 && <Notice>No active meal quantities required.</Notice>}
    {report.data?.requirements.length > 0 && <div className="table-wrap"><table><thead><tr><th scope="col">Purchased meal</th><th scope="col">Quantity required</th></tr></thead>
      <tbody>{report.data.requirements.map(item => <tr key={item.meal_id + ':' + item.purchased_name}><td>{mealLabel(item.purchased_name)}</td><td>{item.quantity}</td></tr>)}</tbody></table></div>}
    <h3>Food orders for this flight</h3>
    {report.data?.orders.length === 0 && <Notice>No food orders for this flight yet.</Notice>}
    {report.data?.orders.map(order => <div key={order.id}><small>Booking #{order.booking_id}</small><FoodOrderDetails order={order} /></div>)}
  </section>
}

import { useState } from 'react'
import { CalendarDays, Plus, Ticket, Users, Armchair } from 'lucide-react'
import { api } from './api'
import { ComplaintList } from './complaints'
import { AdminMealsPanel } from './admin-meals'
import { cabinClasses, cabinLabel } from './travel-options'
import { AirportField, AirportOptions, dateTime, Empty, money, Notice, Status, statuses, useResource } from './ui'

const statusOptions = ['on_time', 'delayed', 'cancelled', 'departed', 'landed']
const indiaOffsetMs = 330 * 60000

function dateInput(value) {
  return value ? new Date(Date.parse(value) + indiaOffsetMs).toISOString().slice(0, 16) : ''
}

function FlightForm({ flight, onClose, onSave }) {
  const [origin, setOrigin] = useState(flight?.origin || '')
  const [destination, setDestination] = useState(flight?.destination || '')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    const form = Object.fromEntries(new FormData(event.currentTarget))
    const payload = {
      ...form,
      number: form.number.trim().toUpperCase(),
      departure: form.departure + ':00+05:30',
      arrival: form.arrival + ':00+05:30',
      capacity: Number(form.capacity),
    }
    setBusy(true)
    setError('')
    try {
      await api('/admin/flights/' + (flight ? flight.id + '/' : ''), {
        method: flight ? 'PATCH' : 'POST', body: payload,
      })
      onSave(flight ? 'Flight updated.' : 'Flight created.')
    } catch (failure) {
      setError(failure.message)
    } finally {
      setBusy(false)
    }
  }

  return <section className="panel editor">
    <h3>{flight ? 'Edit ' + flight.number : 'Add a flight'}</h3>
    <form className="stack" onSubmit={submit}>
      <AirportOptions />
      <div className="editor-grid">
        <label>Flight number<input name="number" defaultValue={flight?.number} placeholder="e.g. AI501"
          maxLength={8} required /></label>
        <label>Airline<input name="airline" defaultValue={flight?.airline} maxLength={80} required /></label>
        <AirportField label="Origin" name="origin" required value={origin} onChange={setOrigin} />
        <AirportField label="Destination" name="destination" required value={destination} onChange={setDestination} />
        <label>Departure (IST)<input type="datetime-local" name="departure" defaultValue={dateInput(flight?.departure)} required /></label>
        <label>Arrival (IST)<input type="datetime-local" name="arrival" defaultValue={dateInput(flight?.arrival)} required /></label>
        <label>Price per seat (INR)<input type="number" name="price" min="0.01" step="0.01" defaultValue={flight?.price} required /></label>
        <label>Capacity<input type="number" name="capacity" min="1" max="1000" defaultValue={flight?.capacity} required /></label>
        <label>Cabin class<select name="cabin_class" defaultValue={flight?.cabin_class || 'economy'}>
          {cabinClasses.map(cabin => <option key={cabin.value} value={cabin.value}>{cabin.label}</option>)}
        </select></label>
        <label>Status<select name="status" defaultValue={flight?.status || 'on_time'}>{statusOptions.map(value =>
          <option key={value} value={value}>{statuses[value]}</option>)}</select></label>
      </div>
      {error && <Notice error>{error}</Notice>}
      <div className="action-row"><button className="button" disabled={busy}>{busy ? 'Saving…' : 'Save flight'}</button>
        <button className="button button-secondary" type="button" disabled={busy} onClick={onClose}>Close</button></div>
    </form>
  </section>
}

function FlightTable({ flights, onEdit, onAction, busy, deleteId, setDeleteId }) {
  return <div className="table-wrap" role="region" aria-label="Flight management table" tabIndex={0}><table>
    <thead><tr><th scope="col">Flight</th><th scope="col">Departure (IST)</th><th scope="col">Fare</th>
      <th scope="col">Seats left</th><th scope="col">Status</th><th scope="col">Actions</th></tr></thead>
    <tbody>{flights.map(flight => <tr key={flight.id}>
      <td><strong>{flight.number} · {flight.origin} → {flight.destination}</strong>
        <small>{flight.airline}</small></td>
      <td>{dateTime(flight.departure)}</td><td>{money(flight.price)}<small>{cabinLabel(flight.cabin_class)}</small></td><td>{flight.seats_available} / {flight.capacity}</td>
      <td><select key={flight.status} aria-label={'Status for ' + flight.number} value={flight.status} disabled={busy}
        onChange={event => onAction('/admin/flights/' + flight.id + '/status/', 'PUT', { status: event.target.value }, 'Flight status updated.')}>
        {statusOptions.map(value => <option key={value} value={value}>{statuses[value]}</option>)}
      </select></td>
      <td><div className="action-row">
        {deleteId === flight.id ? <>
          <button className="button button-small button-danger" disabled={busy}
            onClick={() => onAction('/admin/flights/' + flight.id + '/', 'DELETE', undefined, 'Flight deleted.')}>Confirm delete</button>
          <button className="button button-small button-secondary" disabled={busy} onClick={() => setDeleteId(null)}>Keep</button>
        </> : <>
          <button className="button button-small button-secondary" onClick={() => onEdit(flight)}>Edit</button>
          <button className="button button-small button-secondary" onClick={() => setDeleteId(flight.id)}>Delete</button>
        </>}
      </div></td>
    </tr>)}</tbody>
  </table></div>
}

function UserTable({ users, onAction, busy }) {
  return <div className="table-wrap" role="region" aria-label="User accounts table" tabIndex={0}><table>
    <thead><tr><th scope="col">Account</th><th scope="col">Email</th><th scope="col">Status</th><th scope="col">Actions</th></tr></thead>
    <tbody>{users.map(user => <tr key={user.id}>
      <td><strong>{user.username}</strong><small>{[user.first_name, user.last_name].filter(Boolean).join(' ')}</small></td>
      <td>{user.email}</td><td><Status value={user.approval_status} /></td>
      <td>{user.is_staff ? 'Administrator' : <div className="action-row">
        {user.approval_status !== 'approved' && <button className="button button-small" disabled={busy}
          onClick={() => onAction('/admin/users/' + user.id + '/approve/', 'POST', undefined, 'Account approved.')}>Approve</button>}
        {user.approval_status !== 'rejected' && <button className="button button-small button-secondary" disabled={busy}
          onClick={() => onAction('/admin/users/' + user.id + '/reject/', 'POST', undefined, 'Account rejected.')}>Reject</button>}
      </div>}</td>
    </tr>)}</tbody>
  </table></div>
}

const summaries = [
  ['pending_users', 'Pending users', Users], ['flights', 'Flights', CalendarDays],
  ['confirmed_bookings', 'Confirmed bookings', Ticket], ['confirmed_seats', 'Reserved seats', Armchair],
]

const dashboardSections = {
  pending: ['Registration requests', 'Review new accounts and approve travelers for access.'],
  users: ['Traveler accounts', 'Review account details and manage approval status.'],
  flights: ['Flight management', 'Update schedules, fares, seat availability, and flight status.'],
  complaints: ['Traveler support', 'Review feedback and requests from your travelers.'],
}

export function AdminPage() {
  const [tab, setTab] = useState('pending')
  const [editor, setEditor] = useState(null)
  const [deleteId, setDeleteId] = useState(null)
  const [feedback, setFeedback] = useState(null)
  const [busy, setBusy] = useState(false)
  const [version, setVersion] = useState(0)
  const stats = useResource('/admin/stats/', version)
  const path = { pending: '/admin/users/pending/', users: '/admin/users/', flights: '/admin/flights/', complaints: '/admin/complaints/', meals: '/admin/meals/' }[tab]
  const list = useResource(path, version)

  function saved(message) {
    setEditor(null)
    setDeleteId(null)
    setFeedback({ message })
    setVersion(current => current + 1)
  }

  async function action(path, method, body, message) {
    setBusy(true)
    setFeedback(null)
    try {
      await api(path, { method, body })
      saved(message)
    } catch (failure) {
      setFeedback({ message: failure.message, error: true })
    } finally {
      setBusy(false)
    }
  }

  function switchTo(value) {
    setTab(value)
    setEditor(null)
    setDeleteId(null)
    setFeedback(null)
  }

  return <>
    <div className="page-title"><span className="eyebrow">Operations overview</span><h1>Admin dashboard</h1><p>Keep flights moving. Manage travelers, menus, and availability from one workspace.</p></div>
    {stats.error && <Notice error>{stats.error}</Notice>}
    <div className="stat-grid">
      {summaries.map(([key, label, Icon]) => <div className="panel stat" key={key}>
        <span className="icon-tile"><Icon size={20} aria-hidden="true" /></span>
        <div><small>{label}</small><strong>{stats.data?.[key] ?? '–'}</strong></div>
      </div>)}
    </div>
    <section className="admin-queue">
      <div className="admin-nav">
        <div className="tabs" aria-label="Dashboard sections">
          {[['pending', 'Pending registrations'], ['users', 'All users'], ['flights', 'Flights'], ['meals', 'Meals'], ['complaints', 'Complaints']].map(([value, label]) =>
            <button key={value} type="button" disabled={busy} aria-pressed={tab === value} onClick={() => switchTo(value)}>{label}</button>)}
        </div>
        {tab === 'flights' && <button className="button" onClick={() => setEditor({ create: true })}><Plus size={17} aria-hidden="true" /> Add flight</button>}
        {tab === 'complaints' && <button type="button" className="button button-secondary" disabled={list.loading}
          onClick={() => setVersion(current => current + 1)}>Refresh complaints</button>}
      </div>
      {dashboardSections[tab] && <div className="admin-section-heading"><h2>{dashboardSections[tab][0]}</h2><p>{dashboardSections[tab][1]}</p>
        {tab === 'flights' && <small className="table-hint">On small screens, scroll the table sideways to see all actions.</small>}
      </div>}
      {feedback && <Notice error={feedback.error}>{feedback.message}</Notice>}
      {tab === 'flights' && editor && <FlightForm key={editor.id || 'new'} flight={editor.create ? null : editor}
        onClose={() => setEditor(null)} onSave={saved} />}
      {tab === 'complaints' && <ComplaintList result={list} admin />}
      {tab === 'meals' && <AdminMealsPanel catalog={list} onChanged={saved} />}
      {!['complaints', 'meals'].includes(tab) && list.loading && <Notice>Loading records…</Notice>}
      {!['complaints', 'meals'].includes(tab) && list.error && <Notice error>{list.error}</Notice>}
      {!['complaints', 'meals'].includes(tab) && list.data?.length === 0 && <Empty title={tab === 'pending' ? 'No pending registrations' : 'No records yet'}>
        {tab === 'flights' ? 'Add a flight to make it available for search.' : 'New accounts appear here after registration.'}</Empty>}
      {!['complaints', 'meals'].includes(tab) && list.data?.length > 0 && (tab === 'flights'
        ? <FlightTable flights={list.data} onEdit={setEditor} onAction={action} busy={busy} deleteId={deleteId} setDeleteId={setDeleteId} />
        : <UserTable users={list.data} onAction={action} busy={busy} />)}
    </section>
  </>
}

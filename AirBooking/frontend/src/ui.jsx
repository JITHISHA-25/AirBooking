import { useEffect, useState } from 'react'
import { ArrowRight, CircleAlert, Plane, Radio } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from './api'
import { cabinLabel } from './travel-options'
import { statusSourceLabel } from './display-labels'

export const airports = {
  BLR: 'Bengaluru', BOM: 'Mumbai', CCJ: 'Kozhikode', COK: 'Kochi',
  DEL: 'New Delhi', DXB: 'Dubai', HYD: 'Hyderabad', MAA: 'Chennai', TRV: 'Thiruvananthapuram',
}

export const statuses = {
  unknown: 'Unknown',
  on_time: 'On time', delayed: 'Delayed', cancelled: 'Cancelled', departed: 'Departed',
  landed: 'Landed', confirmed: 'Confirmed', pending: 'Pending', approved: 'Approved', rejected: 'Rejected',
}

export const money = value => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(value)

export function dateTime(value, options = {}) {
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata', ...options,
  }).format(new Date(value))
}

export function duration(flight) {
  const minutes = Math.round((new Date(flight.arrival) - new Date(flight.departure)) / 60000)
  return [Math.floor(minutes / 60) ? Math.floor(minutes / 60) + 'h' : '', minutes % 60 + 'm'].filter(Boolean).join(' ')
}

export function canBook(flight) {
  return ['on_time', 'delayed'].includes(flight.status) && flight.seats_available > 0 && Date.parse(flight.departure) > Date.now()
}

export function Logo() {
  return <Link className="brand" to="/"><span><Plane size={19} aria-hidden="true" /></span>AirBooking</Link>
}

export function Status({ value }) {
  return <span className={'status status-' + value}><i />{statuses[value] || value}</span>
}

export function Notice({ children, error = false }) {
  return <div className={'notice' + (error ? ' notice-error' : '')} role={error ? 'alert' : 'status'}>
    {error && <CircleAlert size={17} aria-hidden="true" />}{children}
  </div>
}

export function Empty({ title, children }) {
  return <div className="empty"><Plane size={25} aria-hidden="true" /><h3>{title}</h3><p>{children}</p></div>
}

export function RouteInfo({ flight }) {
  const time = { dateStyle: undefined }
  return <div className="route-info">
    <div><strong>{flight.origin}</strong><span>{airports[flight.origin] || 'Departure'}</span><small>{dateTime(flight.departure, time)}</small></div>
    <div className="route-line"><small>{duration(flight)}</small><span><Plane size={17} aria-hidden="true" /></span></div>
    <div><strong>{flight.destination}</strong><span>{airports[flight.destination] || 'Arrival'}</span><small>{dateTime(flight.arrival, time)}</small></div>
  </div>
}

export function AirportField({ label, name, value, onChange, required = false }) {
  return <label>{label}<input name={name} value={value} maxLength={3} required={required} pattern="[A-Za-z]{3}" list="airports"
    placeholder={name === 'origin' ? 'e.g. COK' : 'e.g. BLR'} onChange={event => onChange(event.target.value.toUpperCase())} /></label>
}

export function AirportOptions() {
  return <datalist id="airports">{Object.entries(airports).map(([code, city]) =>
    <option key={code} value={code}>{city}</option>)}</datalist>
}

export function FlightCard({ flight, search = '' }) {
  return <article className="flight-card">
    <div className="flight-identity"><span className="icon-tile"><Plane size={20} aria-hidden="true" /></span>
      <div><strong>{flight.airline}</strong><small>{flight.number}</small>
        <small>{dateTime(flight.departure, { timeStyle: undefined })}</small></div>
    </div>
    <RouteInfo flight={flight} />
    <div className="fare"><Status value={flight.status} /><small>{cabinLabel(flight.cabin_class)}</small><strong>{money(flight.price)}</strong>
      <small>{flight.seats_available} seats left · per seat</small>
      <Link className="button button-small" to={'/flights/' + flight.id + (search ? '?' + search : '')}>View flight <ArrowRight size={15} aria-hidden="true" /></Link>
    </div>
  </article>
}

const loading = { data: null, error: '', loading: true }

export function useResource(path, version = 0) {
  const [result, setResult] = useState(null)
  useEffect(() => {
    const controller = new AbortController()
    api(path, { signal: controller.signal })
      .then(data => {
        if (!controller.signal.aborted) setResult({ path, version, data, loading: false, error: '' })
      })
      .catch(error => {
        if (!controller.signal.aborted) setResult({ path, version, data: null, loading: false, error: error.message })
      })
    return () => controller.abort()
  }, [path, version])
  return result?.path === path && result.version === version ? result : loading
}

export function LiveStatus({ flight, enabled = true }) {
  const [live, setLive] = useState(null)
  useEffect(() => {
    const controller = new AbortController()
    let timer
    setLive(null)
    async function update() {
      try {
        const data = await api('/flights/' + flight.id + '/status/', { signal: controller.signal })
        if (!controller.signal.aborted) setLive(data)
      } catch {
        if (!controller.signal.aborted) setLive(null)
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(update, 30000)
      }
    }
    if (enabled) update()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [flight.id, enabled])
  const source = live?.source || 'airbooking'
  return <div className="live-status"><Status value={live?.status || flight.status} />
    <span><Radio size={14} aria-hidden="true" />
      {statusSourceLabel(source)}
      {live && enabled ? ' · Refreshes every 30s' : ''}
    </span>
  </div>
}

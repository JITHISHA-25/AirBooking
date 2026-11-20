import { useState } from 'react'
import { Radio, RefreshCw, Search } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { statusSourceLabel } from './display-labels'
import { AirportField, AirportOptions, dateTime, Empty, Notice, Status, useResource } from './ui'

const modes = [['airport', 'By Airport'], ['route', 'By Route'], ['flight_number', 'By Flight Number']]
function today() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
}

export function FlightStatusPage() {
  const [params, setParams] = useSearchParams()
  const search = params.toString()
  return <>
    <div className="page-title"><h1>Flight Status</h1><p>Check departures, arrivals and flight updates.</p></div>
    <StatusSearchForm key={search} params={params} onSearch={setParams} />
    {params.has('mode') ? <StatusResults search={search} /> : <Notice>Choose a search mode, enter your details and select Check status.</Notice>}
  </>
}

function StatusSearchForm({ params, onSearch }) {
  const [mode, setMode] = useState(modes.some(([key]) => key === params.get('mode')) ? params.get('mode') : 'airport')
  const [form, setForm] = useState({ airport: params.get('airport') || '', origin: params.get('origin') || '',
    destination: params.get('destination') || '', date: params.get('date') || today(),
    direction: params.get('direction') === 'arrivals' ? 'arrivals' : 'departures', flight_number: params.get('flight_number') || '' })
  function set(field, value) { setForm(previous => ({ ...previous, [field]: value })) }
  function submit(event) {
    event.preventDefault()
    const query = { mode, date: form.date }
    if (mode === 'airport') {
      query.airport = form.airport
      query.direction = form.direction
      const optional = form.direction === 'arrivals' ? 'origin' : 'destination'
      if (form[optional]) query[optional] = form[optional]
    } else if (mode === 'route') {
      query.origin = form.origin
      query.destination = form.destination
    } else query.flight_number = form.flight_number.replace(/\s+/g, '').toUpperCase()
    onSearch(query)
  }
  return <section className="panel stack">
    <div className="tabs" aria-label="Flight status search modes">{modes.map(([key, label]) =>
      <button key={key} type="button" aria-pressed={mode === key} onClick={() => setMode(key)}>{label}</button>)}</div>
    <form className="status-search-form" onSubmit={submit}>
      <AirportOptions />
      {mode === 'airport' && <>
        <AirportField label="Airport" name="airport" required value={form.airport} onChange={value => set('airport', value)} />
        <label>Board<select value={form.direction} onChange={event => set('direction', event.target.value)}>
          <option value="departures">Departures</option><option value="arrivals">Arrivals</option>
        </select></label>
        {form.direction === 'departures'
          ? <AirportField label="Destination (optional)" name="destination" value={form.destination} onChange={value => set('destination', value)} />
          : <AirportField label="Origin (optional)" name="origin" value={form.origin} onChange={value => set('origin', value)} />}
      </>}
      {mode === 'route' && <>
        <AirportField label="Origin" name="origin" required value={form.origin} onChange={value => set('origin', value)} />
        <AirportField label="Destination" name="destination" required value={form.destination} onChange={value => set('destination', value)} />
      </>}
      {mode === 'flight_number' && <label>Flight number<input value={form.flight_number} maxLength={20} required placeholder="e.g. 6E 2009"
        onChange={event => set('flight_number', event.target.value.toUpperCase())} /></label>}
      <label>{mode === 'airport' && form.direction === 'arrivals' ? 'Arrival date' : 'Departure date'}
        <input type="date" required value={form.date} onChange={event => set('date', event.target.value)} />
      </label>
      <button className="button"><Search size={17} aria-hidden="true" /> Check status</button>
    </form>
    <small>Dates and flight times use the relevant airport’s local time. Live schedules have limited date coverage.</small>
  </section>
}

function FlightTimes({ label, code, times }) {
  const show = value => value ? value.replace('T', ' ').slice(0, 16) : 'Not available'
  return <div className="status-flight-times">
    <h3>{label} · {code}</h3>
    <dl><div><dt>Scheduled</dt><dd>{show(times.scheduled)}</dd></div>
      {times.estimated && <div><dt>Estimated</dt><dd>{show(times.estimated)}</dd></div>}
      {times.actual && <div><dt>Actual</dt><dd>{show(times.actual)}</dd></div>}
      {times.terminal && <div><dt>Terminal</dt><dd>{times.terminal}</dd></div>}
      {times.gate && <div><dt>Gate</dt><dd>{times.gate}</dd></div>}
      {times.delay_minutes !== null && <div><dt>Delay</dt><dd>{times.delay_minutes} min</dd></div>}
    </dl>
  </div>
}

function StatusResults({ search }) {
  const [version, setVersion] = useState(0)
  const result = useResource('/flights/status/search/?' + search, version)
  const data = result.data
  return <section className="results" aria-labelledby="status-results-title" aria-busy={result.loading}>
    <div className="section-heading flight-results-heading"><div className="flight-results-title">
      <h2 id="status-results-title">Flight updates</h2>{data && <span>{data.results.length} {data.results.length === 1 ? 'flight' : 'flights'}</span>}</div>
      <button type="button" className="button button-secondary" disabled={result.loading} onClick={() => setVersion(value => value + 1)}>
        <RefreshCw size={16} aria-hidden="true" /> Refresh</button>
    </div>
    {result.loading && <Notice>Checking flight status...</Notice>}
    {result.error && <Notice error>{result.error}</Notice>}
    {data && <>
      <p className="status-checked">Last checked {dateTime(data.checked_at)} IST · Updates may be cached for up to 45 seconds.</p>
      <Notice>{data.state === 'unavailable' ? 'Provider unavailable. ' : data.state === 'outside_coverage' ? 'Date outside live coverage. ' : ''}{data.message}</Notice>
      {data.partial && <Notice>Partial results: the search reached its limit, or some provider records/pages could not be read.</Notice>}
      {data.state === 'empty' && <Empty title="No matching flights">The provider returned no matches within its available live window. Try another route, airport or date.</Empty>}
      <div className="cards">{data.results.map((flight, index) => <article className="panel status-flight-card" key={flight.number + flight.dep.scheduled + index}>
        <div className="section-heading"><div><h3>{flight.number} · {flight.origin} → {flight.destination}</h3>
          {flight.airline && <p>{flight.airline}</p>}</div><Status value={flight.status} /></div>
        <div className="status-times-grid"><FlightTimes label="Departure" code={flight.origin} times={flight.dep} />
          <FlightTimes label="Arrival" code={flight.destination} times={flight.arr} /></div>
        <div className="status-source"><span><Radio size={14} aria-hidden="true" /> Source: {statusSourceLabel(flight.source)}</span>
          {flight.baggage && <span>Baggage belt: {flight.baggage}</span>}</div>
      </article>)}</div>
    </>}
  </section>
}

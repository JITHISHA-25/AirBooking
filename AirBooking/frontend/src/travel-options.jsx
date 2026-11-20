import { useEffect, useRef, useState } from 'react'
import { Armchair, ChevronDown, Coffee, ConciergeBell, DoorOpen, Luggage, Sparkles, Utensils, X } from 'lucide-react'

export const cabinClasses = [
  { value: 'economy', label: 'Economy', benefits: [] },
  { value: 'premium_economy', label: 'Premium Economy', benefits: [[Armchair, 'Extra Legroom'], [Luggage, 'Extra Baggage'], [Utensils, 'Premium Meals']] },
  { value: 'business', label: 'Business Class', benefits: [[Coffee, 'Luxury Lounges'], [Armchair, 'Cabin Comfort'], [Utensils, 'Premium Dining']] },
  { value: 'first', label: 'First Class', benefits: [[DoorOpen, 'Private Suites'], [Utensils, 'Fine Dining'], [ConciergeBell, 'Highly Personalised Service']] },
]

export const cabinLabel = value => cabinClasses.find(cabin => cabin.value === value)?.label || 'Economy'
export const travellerCount = value => value.adults + value.children + value.infants
export const travellerSummary = value => [
  `${value.adults} ${value.adults === 1 ? 'adult' : 'adults'}`,
  value.children ? `${value.children} ${value.children === 1 ? 'child' : 'children'}` : '',
  value.infants ? `${value.infants} ${value.infants === 1 ? 'infant' : 'infants'}` : '',
].filter(Boolean).join(', ')

const ageGroups = [
  { field: 'adults', label: 'Adults', age: '12 years and above', min: 1, max: 9 },
  { field: 'children', label: 'Children', age: '2 to under 12 years', min: 0, max: 6 },
  { field: 'infants', label: 'Infants', age: 'Below 2 years', min: 0, max: 6 },
]

export function TravelOptions({ value, onChange, disabled = false, cabinSelection = true }) {
  const [panel, setPanel] = useState(null)
  const [groupNote, setGroupNote] = useState(false)
  const dialog = useRef(null)
  const trigger = useRef(null)
  useEffect(() => {
    if (panel && !dialog.current.open) dialog.current.showModal()
    if (!panel && dialog.current.open) dialog.current.close()
  }, [panel])

  function open(event, section) {
    trigger.current = event.currentTarget
    setGroupNote(false)
    setPanel(section)
  }

  function close() {
    dialog.current.close()
    setPanel(null)
    trigger.current?.focus()
  }

  const count = travellerCount(value)
  return <>
    <div className="search-picker">
      <span>Travellers</span>
      <button type="button" className="picker-trigger" disabled={disabled} aria-haspopup="dialog"
        onClick={event => open(event, 'travellers')}>
        <span>{count} {count === 1 ? 'Traveller' : 'Travellers'}</span><ChevronDown size={16} aria-hidden="true" />
      </button>
    </div>
    {cabinSelection && <div className="search-picker cabin-picker">
      <span>Cabin class</span>
      <button type="button" className="picker-trigger" disabled={disabled} aria-haspopup="dialog"
        onClick={event => open(event, 'cabin')}>
        <span>{cabinClasses.find(cabin => cabin.value === value.cabin_class)?.searchLabel || cabinLabel(value.cabin_class)}</span>
        <ChevronDown size={16} aria-hidden="true" />
      </button>
    </div>}
    <dialog ref={dialog} className={'travel-dialog ' + (panel === 'cabin' ? 'cabin-dialog' : '')}
      aria-label={panel === 'cabin' ? 'Choose cabin class' : 'Choose travellers'} onCancel={event => { event.preventDefault(); close() }}>
      <div className="section-heading"><h2>{panel === 'cabin' ? 'Choose cabin class' : 'Choose travellers'}</h2>
        <button type="button" className="icon-button" aria-label="Close travel options" onClick={close}><X size={19} aria-hidden="true" /></button>
      </div>
      {panel === 'travellers' ? <>
        <div className="traveller-groups">{ageGroups.map(({ field, label, age, min, max }) =>
          <fieldset className={'traveller-group traveller-' + field} key={field}>
            <legend><strong>{label} <span>({age})</span></strong><small>On the day of travel</small></legend>
            <div className="count-options">{Array.from({ length: max - min + 1 }, (_, index) => index + min).map(number => {
              const proposed = { ...value, [field]: number }
              const unavailable = travellerCount(proposed) > 9 || proposed.infants > proposed.adults
              return <button key={number} type="button" aria-label={`${number} ${label.toLowerCase()}`}
                aria-pressed={value[field] === number} disabled={unavailable}
                onClick={() => { setGroupNote(false); onChange(proposed) }}>{number}</button>
            })}
              <button type="button" aria-label={`More than ${max} ${label.toLowerCase()}`} onClick={() => setGroupNote(true)}>&gt;{max}</button>
            </div>
          </fieldset>)}</div>
        <p className="traveller-rules">Up to 9 travellers per booking. Each infant needs an accompanying adult.</p>
        <p className="traveller-rules">Each traveller, including infants, reserves one seat at the listed fare.</p>
        {groupNote && <p className="notice" role="status">For larger parties or more than 6 children or infants, contact the airline for a group booking.</p>}
        <div className="picker-actions"><small aria-live="polite">{travellerSummary(value)}</small>
          <button type="button" className="button" onClick={() => cabinSelection ? setPanel('cabin') : close()}>{cabinSelection ? 'Next' : 'Done'}</button></div>
      </> : <>
        <div className="cabin-options">{cabinClasses.map(cabin => <label key={cabin.value}
          className={'cabin-option' + (value.cabin_class === cabin.value ? ' selected' : '')}>
          <input type="radio" name="cabin-class" value={cabin.value} checked={value.cabin_class === cabin.value}
            onChange={() => onChange({ ...value, cabin_class: cabin.value })} />
          <div><strong>{cabin.searchLabel || cabin.label}</strong>
            {cabin.benefits.length > 0 && <div className="cabin-benefits">{cabin.benefits.map(([Icon, text]) =>
              <span key={text}><Icon size={16} aria-hidden="true" />{text}</span>)}</div>}
          </div>
          <span className={'cabin-art cabin-art-' + cabin.value} aria-hidden="true"><Armchair size={52} strokeWidth={1.5} />
            {cabin.value === 'first' && <Sparkles size={18} />}</span>
        </label>)}</div>
        <p className="traveller-rules">Cabin benefits vary by airline. Check with your airline before booking.</p>
        <div className="picker-actions"><button type="button" className="button button-secondary" onClick={() => setPanel('travellers')}>Back</button>
          <button type="button" className="button" onClick={close}>Done</button></div>
      </>}
    </dialog>
  </>
}

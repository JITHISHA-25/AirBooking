import { Building2, CreditCard, Smartphone } from 'lucide-react'

const methods = [
  { value: 'card', label: 'Card', detail: 'Test card ending in 4242', Icon: CreditCard },
  { value: 'upi', label: 'UPI', detail: 'test@airbooking', Icon: Smartphone },
  { value: 'bank', label: 'Net banking', detail: 'AirBooking Test Bank', Icon: Building2 },
]

export function SimulationControls({ method, setMethod, outcome, setOutcome, disabled, prefix = 'payment' }) {
  return <>
    <fieldset className="payment-choice-group" disabled={disabled}>
      <legend>Payment method</legend>
      {methods.map(({ value, label, detail, Icon }) => <label key={value} className={'payment-method' + (method === value ? ' selected' : '')}>
        <input type="radio" name={prefix + '-method'} value={value} checked={method === value} onChange={() => setMethod(value)} />
        <Icon size={22} aria-hidden="true" /><span><strong>{label}</strong><small>{detail}</small></span>
      </label>)}
    </fieldset>
    <fieldset className="payment-choice-group payment-outcomes" disabled={disabled}>
      <legend>Simulation outcome</legend>
      <label><input type="radio" name={prefix + '-outcome'} checked={outcome === 'success'} onChange={() => setOutcome('success')} /> Successful payment</label>
      <label><input type="radio" name={prefix + '-outcome'} checked={outcome === 'decline'} onChange={() => setOutcome('decline')} /> Declined payment</label>
    </fieldset>
  </>
}

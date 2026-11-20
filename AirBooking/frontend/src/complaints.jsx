import { useState } from 'react'
import { MessageSquare } from 'lucide-react'
import { api } from './api'
import { dateTime, Notice, useResource } from './ui'

const commonComplaints = [
  'Flight delayed',
  'Flight cancelled',
  'Booking confirmation not received',
  'Payment issue or duplicate charge',
  'Refund not received',
  'Seat reservation issue',
  'Baggage lost or damaged',
  'Poor customer service',
]

export function ComplaintList({ result, admin = false }) {
  return <>
    {result.loading && <Notice>Loading complaints...</Notice>}
    {result.error && <Notice error>{result.error}</Notice>}
    {result.data?.length === 0 && <div className="empty">
      <MessageSquare size={25} aria-hidden="true" /><h3>No complaints yet</h3>
      <p>{admin ? 'Complaints submitted by users will appear here.' : 'Your submitted complaints will appear here.'}</p>
    </div>}
    <div className="cards">{result.data?.map(complaint => <article className="panel complaint-card" key={complaint.id}>
      <div className="section-heading"><h3>{complaint.subject}</h3><small>#{complaint.id}</small></div>
      {admin && <p className="complaint-sender"><strong>{complaint.username}</strong> &middot; {complaint.email}</p>}
      <small>Submitted {dateTime(complaint.created_at)} IST</small>
      <p className="complaint-message">{complaint.message}</p>
    </article>)}</div>
  </>
}

export function ComplaintsPage() {
  const [subject, setSubject] = useState('')
  const [version, setVersion] = useState(0)
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState(null)
  const result = useResource('/complaints/', version)

  async function submit(event) {
    event.preventDefault()
    const form = event.currentTarget
    const body = Object.fromEntries(new FormData(form))
    setBusy(true)
    setFeedback(null)
    try {
      await api('/complaints/', { method: 'POST', body })
      form.reset()
      setSubject('')
      setFeedback({ message: 'Your complaint has been submitted for the admin to review.' })
      setVersion(current => current + 1)
    } catch (failure) {
      setFeedback({ message: failure.message, error: true })
    } finally {
      setBusy(false)
    }
  }

  return <>
    <div className="page-title"><h1>Complaints</h1><p>Tell us about an issue with your flight, booking or experience.</p></div>
    <section className="panel stack" aria-labelledby="new-complaint-title">
      <h2 id="new-complaint-title">Submit a complaint</h2>
      <form className="stack" onSubmit={submit}>
        <label>Common complaints<select disabled={busy}
          value={commonComplaints.includes(subject) ? subject : ''}
          onChange={event => setSubject(event.target.value)}>
          <option value="">Other / write your own subject</option>
          {commonComplaints.map(complaint => <option key={complaint} value={complaint}>{complaint}</option>)}
        </select></label>
        <label>Subject<input name="subject" value={subject} onChange={event => setSubject(event.target.value)}
          maxLength={160} required disabled={busy} placeholder="Briefly describe the issue" />
          <small>Choose a common complaint above, or type your own subject. You can edit any selected subject.</small>
        </label>
        <label>Message<textarea name="message" rows={5} maxLength={5000} required disabled={busy}
          placeholder="Describe what happened. Include your booking reference if relevant." /></label>
        <small>Up to 5,000 characters. Please do not include passwords or payment details.</small>
        {feedback && <Notice error={feedback.error}>{feedback.message}</Notice>}
        <div><button className="button" disabled={busy}>{busy ? 'Submitting...' : 'Submit complaint'}</button></div>
      </form>
    </section>
    <section className="results" aria-labelledby="my-complaints-title">
      <div className="section-heading"><h2 id="my-complaints-title">My complaints</h2>
        <button type="button" className="button button-secondary button-small" disabled={result.loading}
          onClick={() => setVersion(current => current + 1)}>Refresh</button></div>
      <ComplaintList result={result} />
    </section>
  </>
}
